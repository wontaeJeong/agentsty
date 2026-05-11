package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"agentcask/internal/controller"
	"agentcask/internal/kube"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
)

func main() {
	namespace := flag.String("namespace", envDefault("SESSION_NAMESPACE", kube.DefaultSessionNamespace), "AgentSession namespace")
	kubeconfig := flag.String("kubeconfig", os.Getenv("KUBECONFIG"), "kubeconfig path")
	runtimeImage := flag.String("runtime-image", envDefault("AGENT_RUNTIME_IMAGE", "agentcask/agent-runtime:dev"), "Agent runtime image")
	modelProxyURL := flag.String("model-proxy-url", envDefault("CASK_MODEL_PROXY_URL", "http://cask-model-proxy.agentcask-system.svc.cluster.local:8080/internal/model-proxy/v1"), "internal model proxy URL")
	tokenSecret := flag.String("token-secret", envDefault("CASK_TOKEN_SECRET", "dev-session-proxy-secret"), "session proxy token HMAC secret")
	flag.Parse()
	cfg, err := kube.Config(*kubeconfig)
	if err != nil {
		fatal(err)
	}
	dyn, err := dynamic.NewForConfig(cfg)
	if err != nil {
		fatal(err)
	}
	ks, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		fatal(err)
	}
	r := &controller.Reconciler{Dynamic: dyn, Kube: ks, Config: controller.Config{Namespace: *namespace, RuntimeImage: *runtimeImage, ModelProxyURL: *modelProxyURL, TokenSecret: *tokenSecret}}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	fmt.Printf("cask-controller watching namespace %s\n", *namespace)
	if err := r.Run(ctx); err != nil && ctx.Err() == nil {
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
