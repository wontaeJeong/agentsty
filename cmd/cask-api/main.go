package main

import (
	"context"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	caskapi "agentcask/internal/api"
	"agentcask/internal/kube"
	"agentcask/internal/terminal"
)

func main() {
	addr := flag.String("addr", envDefault("CASK_API_ADDR", ":8080"), "listen address")
	namespace := flag.String("namespace", envDefault("SESSION_NAMESPACE", kube.DefaultSessionNamespace), "AgentSession namespace")
	kubeconfig := flag.String("kubeconfig", os.Getenv("KUBECONFIG"), "kubeconfig path")
	memory := flag.Bool("memory", os.Getenv("CASK_MEMORY") == "1", "use in-memory store and echo terminal")
	flag.Parse()

	var store caskapi.Store
	var termBackend terminal.ExecBackend
	if *memory {
		store = caskapi.NewMemoryStore(true)
		termBackend = terminal.EchoBackend{}
	} else {
		cfg, err := kube.Config(*kubeconfig)
		if err != nil {
			fatal(err)
		}
		sessionClient, kubeClient, err := kube.NewForConfig(cfg, *namespace)
		if err != nil {
			fatal(err)
		}
		store = sessionClient
		termBackend = terminal.KubernetesExecBackend{Client: kubeClient, Config: cfg}
	}
	server := &http.Server{
		Addr: *addr,
		Handler: (&caskapi.Server{
			Store:     store,
			Namespace: *namespace,
			Terminal:  &terminal.Gateway{Resolver: store, Backend: termBackend},
		}).Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()
	fmt.Printf("cask-api listening on %s\n", *addr)
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

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
