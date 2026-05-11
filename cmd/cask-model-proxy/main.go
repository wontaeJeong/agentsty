package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"agentcask/internal/kube"
	"agentcask/internal/modelproxy"
)

func main() {
	addr := flag.String("addr", envDefault("CASK_MODEL_PROXY_ADDR", ":8080"), "listen address")
	namespace := flag.String("namespace", envDefault("SESSION_NAMESPACE", kube.DefaultSessionNamespace), "AgentSession namespace")
	kubeconfig := flag.String("kubeconfig", os.Getenv("KUBECONFIG"), "kubeconfig path")
	upstreamURL := flag.String("upstream-url", os.Getenv("CASK_UPSTREAM_URL"), "model upstream URL")
	upstreamKey := flag.String("upstream-key", os.Getenv("CASK_UPSTREAM_API_KEY"), "model upstream key held only by cask-model-proxy")
	tokenSecret := flag.String("token-secret", envDefault("CASK_TOKEN_SECRET", "dev-session-proxy-secret"), "session proxy token HMAC secret")
	flag.Parse()

	cfg, err := kube.Config(*kubeconfig)
	if err != nil {
		fatal(err)
	}
	sessions, _, err := kube.NewForConfig(cfg, *namespace)
	if err != nil {
		fatal(err)
	}
	proxy := &modelproxy.Proxy{
		Tokens:      modelproxy.TokenManager{Secret: *tokenSecret},
		Sessions:    sessions,
		UpstreamURL: *upstreamURL,
		UpstreamKey: *upstreamKey,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if err := sessions.Ready(r.Context()); err != nil {
			http.Error(w, "not ready", http.StatusServiceUnavailable)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})
	mux.HandleFunc("/internal/model-proxy/v1/chat/completions", proxy.Handler)

	server := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()
	fmt.Printf("cask-model-proxy listening on %s\n", *addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		fatal(err)
	}
}

func envDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
