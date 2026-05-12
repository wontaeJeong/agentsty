package controller

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"agentcask/internal/isolation"
	"agentcask/internal/kube"
	"agentcask/internal/redact"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	kubefake "k8s.io/client-go/kubernetes/fake"
)

func testSession(profile string) *agentv1.AgentSession {
	now := metav1.NewTime(time.Now().UTC())
	s := agentv1.NewAgentSession("sess-test", kube.DefaultSessionNamespace, agentv1.AgentSessionSpec{UserID: "dev-user", Tool: "stub", Repo: agentv1.RepoSpec{URL: "https://example.invalid/repo.git", Branch: "main"}, ModelRef: "default", ResourceProfile: "small", Isolation: agentv1.IsolationSpec{Profile: profile}, TTLSeconds: 7200}, now)
	s.UID = "uid-test"
	return s
}

func TestBuildPodUsesProxyTokenNotUpstreamKey(t *testing.T) {
	session := testSession("default")
	pod := BuildPod(session, DefaultConfig(), isolation.Profile{})
	data, _ := json.Marshal(pod)
	if strings.Contains(string(data), redact.Sentinel) {
		t.Fatalf("pod leaked upstream sentinel: %s", data)
	}
	if strings.Contains(string(data), "privileged") {
		t.Fatalf("pod should not request privileged mode: %s", data)
	}
	if pod.Spec.RuntimeClassName != nil {
		t.Fatal("default isolation set runtimeClassName")
	}
	container := pod.Spec.Containers[0]
	foundProxyURL := false
	foundProxyToken := false
	for _, env := range container.Env {
		if env.Name == "CASK_MODEL_BASE_URL" {
			foundProxyURL = true
		}
		if env.Name == "CASK_SESSION_TOKEN" && strings.HasPrefix(env.Value, "cask-proxy.") {
			foundProxyToken = true
		}
	}
	if !foundProxyURL || !foundProxyToken {
		t.Fatalf("pod env missing proxy URL/token: %#v", container.Env)
	}
}

func TestBuildPodAppliesKataProfile(t *testing.T) {
	session := testSession("kata")
	pod := BuildPod(session, DefaultConfig(), isolation.Profile{RuntimeClassName: "kata"})
	if pod.Spec.RuntimeClassName == nil || *pod.Spec.RuntimeClassName != "kata" {
		t.Fatalf("kata runtimeClassName missing: %#v", pod.Spec.RuntimeClassName)
	}
}

func TestBuildPodSmallProfileCanStartOpenCode(t *testing.T) {
	session := testSession("default")
	session.Spec.Tool = "opencode"
	pod := BuildPod(session, DefaultConfig(), isolation.Profile{})
	limit := pod.Spec.Containers[0].Resources.Limits.Memory()
	if limit == nil || limit.Cmp(resource.MustParse("256Mi")) < 0 {
		t.Fatalf("small profile memory limit should support opencode startup, got %v", limit)
	}
}

func TestReconcileCreatesPodAndUpdatesStatus(t *testing.T) {
	ctx := context.Background()
	session := testSession("default")
	dyn := dynamicfake.NewSimpleDynamicClient(runtime.NewScheme(), kube.ToUnstructured(session))
	ks := kubefake.NewClientset()
	r := &Reconciler{Dynamic: dyn, Kube: ks, Config: DefaultConfig()}
	if err := r.Reconcile(ctx, session.Name); err != nil {
		t.Fatal(err)
	}
	pod, err := ks.CoreV1().Pods(kube.DefaultSessionNamespace).Get(ctx, PodName(session.Name), metav1.GetOptions{})
	if err != nil {
		t.Fatalf("pod not created: %v", err)
	}
	if pod.Spec.ServiceAccountName != "agent-session" {
		t.Fatalf("unexpected service account %q", pod.Spec.ServiceAccountName)
	}
	updated, err := dyn.Resource(agentv1.GVR).Namespace(kube.DefaultSessionNamespace).Get(ctx, session.Name, metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
	status, _, _ := unstructured.NestedMap(updated.Object, "status")
	if status["phase"] != agentv1.PhaseProvisioning {
		t.Fatalf("unexpected status: %#v", status)
	}
}

func TestReconcileFailsMissingRuntimeClass(t *testing.T) {
	ctx := context.Background()
	session := testSession("kata")
	dyn := dynamicfake.NewSimpleDynamicClient(runtime.NewScheme(), kube.ToUnstructured(session))
	ks := kubefake.NewClientset()
	r := &Reconciler{Dynamic: dyn, Kube: ks, Config: DefaultConfig()}
	if err := r.Reconcile(ctx, session.Name); err != nil {
		t.Fatal(err)
	}
	updated, err := dyn.Resource(agentv1.GVR).Namespace(kube.DefaultSessionNamespace).Get(ctx, session.Name, metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
	status, _, _ := unstructured.NestedMap(updated.Object, "status")
	if status["reason"] != agentv1.ReasonRuntimeClassNotFound {
		t.Fatalf("unexpected status: %#v", status)
	}
}

var _ = corev1.PodRunning
