package kube

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

const DefaultSessionNamespace = "agentcask-sessions"

type SessionClient struct {
	Dynamic   dynamic.Interface
	Namespace string
}

func Config(kubeconfig string) (*rest.Config, error) {
	if kubeconfig != "" {
		return clientcmd.BuildConfigFromFlags("", kubeconfig)
	}
	if cfg, err := rest.InClusterConfig(); err == nil {
		return cfg, nil
	}
	if env := os.Getenv("KUBECONFIG"); env != "" {
		return clientcmd.BuildConfigFromFlags("", env)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	return clientcmd.BuildConfigFromFlags("", filepath.Join(home, ".kube", "config"))
}

func NewForConfig(cfg *rest.Config, namespace string) (*SessionClient, kubernetes.Interface, error) {
	dyn, err := dynamic.NewForConfig(cfg)
	if err != nil {
		return nil, nil, err
	}
	ks, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return nil, nil, err
	}
	if namespace == "" {
		namespace = DefaultSessionNamespace
	}
	return &SessionClient{Dynamic: dyn, Namespace: namespace}, ks, nil
}

func (c *SessionClient) resource() dynamic.ResourceInterface {
	return c.Dynamic.Resource(agentv1.GVR).Namespace(c.Namespace)
}

func (c *SessionClient) Ready(ctx context.Context) error {
	_, err := c.resource().List(ctx, metav1.ListOptions{Limit: 1})
	return err
}

func (c *SessionClient) Create(ctx context.Context, session *agentv1.AgentSession) (*agentv1.AgentSession, error) {
	u := ToUnstructured(session)
	created, err := c.resource().Create(ctx, u, metav1.CreateOptions{})
	if err != nil {
		return nil, err
	}
	out, err := FromUnstructured(created)
	if err != nil {
		return nil, err
	}
	if out.Status.Phase == "" {
		out.Status = session.Status
	}
	return out, nil
}

func (c *SessionClient) List(ctx context.Context, userID string) ([]agentv1.AgentSession, error) {
	items, err := c.resource().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}
	sessions := make([]agentv1.AgentSession, 0, len(items.Items))
	for i := range items.Items {
		s, err := FromUnstructured(&items.Items[i])
		if err != nil {
			return nil, err
		}
		if userID == "" || s.Spec.UserID == userID {
			sessions = append(sessions, *s)
		}
	}
	return sessions, nil
}

func (c *SessionClient) Get(ctx context.Context, name string) (*agentv1.AgentSession, error) {
	u, err := c.resource().Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		return nil, err
	}
	return FromUnstructured(u)
}

func (c *SessionClient) Delete(ctx context.Context, name string) error {
	return c.resource().Delete(ctx, name, metav1.DeleteOptions{})
}

func (c *SessionClient) PatchStatus(ctx context.Context, name string, status agentv1.AgentSessionStatus) error {
	obj := map[string]any{"status": StatusToMap(status)}
	data, err := jsonMarshal(obj)
	if err != nil {
		return err
	}
	_, err = c.resource().Patch(ctx, name, types.MergePatchType, data, metav1.PatchOptions{}, "status")
	return err
}

func (c *SessionClient) PatchFinalizers(ctx context.Context, name string, finalizers []string) error {
	obj := map[string]any{"metadata": map[string]any{"finalizers": finalizers}}
	data, err := jsonMarshal(obj)
	if err != nil {
		return err
	}
	_, err = c.resource().Patch(ctx, name, types.MergePatchType, data, metav1.PatchOptions{})
	return err
}

func ToUnstructured(session *agentv1.AgentSession) *unstructured.Unstructured {
	u := &unstructured.Unstructured{Object: map[string]any{
		"apiVersion": agentv1.GroupVersion.String(),
		"kind":       agentv1.Kind,
		"metadata": map[string]any{
			"name":      session.Name,
			"namespace": session.Namespace,
			"labels":    stringMapToInterface(session.Labels),
		},
		"spec": SpecToMap(session.Spec),
	}}
	if len(session.Finalizers) > 0 {
		_ = unstructured.SetNestedStringSlice(u.Object, session.Finalizers, "metadata", "finalizers")
	}
	if session.UID != "" {
		u.SetUID(session.UID)
	}
	if session.Status.Phase != "" {
		u.Object["status"] = StatusToMap(session.Status)
	}
	return u
}

func FromUnstructured(u *unstructured.Unstructured) (*agentv1.AgentSession, error) {
	if u == nil {
		return nil, errors.New("nil AgentSession object")
	}
	s := &agentv1.AgentSession{
		TypeMeta: metav1.TypeMeta{APIVersion: agentv1.GroupVersion.String(), Kind: agentv1.Kind},
		ObjectMeta: metav1.ObjectMeta{
			Name:              u.GetName(),
			Namespace:         u.GetNamespace(),
			UID:               u.GetUID(),
			Labels:            u.GetLabels(),
			Finalizers:        u.GetFinalizers(),
			CreationTimestamp: u.GetCreationTimestamp(),
			DeletionTimestamp: u.GetDeletionTimestamp(),
		},
	}
	spec, ok, err := unstructured.NestedMap(u.Object, "spec")
	if err != nil {
		return nil, err
	}
	if ok {
		s.Spec = SpecFromMap(spec)
	}
	status, ok, err := unstructured.NestedMap(u.Object, "status")
	if err != nil {
		return nil, err
	}
	if ok {
		s.Status = StatusFromMap(status)
	}
	return s, nil
}

func SpecToMap(spec agentv1.AgentSessionSpec) map[string]any {
	return map[string]any{
		"userId":          spec.UserID,
		"tool":            spec.Tool,
		"repo":            map[string]any{"url": spec.Repo.URL, "branch": spec.Repo.Branch},
		"modelRef":        spec.ModelRef,
		"resourceProfile": spec.ResourceProfile,
		"isolation":       map[string]any{"profile": spec.Isolation.Profile},
		"ttlSeconds":      spec.TTLSeconds,
	}
}

func SpecFromMap(m map[string]any) agentv1.AgentSessionSpec {
	repo, _, _ := unstructured.NestedMap(m, "repo")
	isolation, _, _ := unstructured.NestedMap(m, "isolation")
	return agentv1.AgentSessionSpec{
		UserID:          stringValue(m["userId"]),
		Tool:            stringValue(m["tool"]),
		Repo:            agentv1.RepoSpec{URL: stringValue(repo["url"]), Branch: stringValue(repo["branch"])},
		ModelRef:        stringValue(m["modelRef"]),
		ResourceProfile: stringValue(m["resourceProfile"]),
		Isolation:       agentv1.IsolationSpec{Profile: stringValue(isolation["profile"])},
		TTLSeconds:      int64Value(m["ttlSeconds"]),
	}
}

func StatusToMap(status agentv1.AgentSessionStatus) map[string]any {
	m := map[string]any{
		"phase":         status.Phase,
		"reason":        status.Reason,
		"message":       status.Message,
		"podName":       status.PodName,
		"containerName": status.ContainerName,
		"terminalReady": status.TerminalReady,
	}
	if status.CreatedAt != nil {
		m["createdAt"] = status.CreatedAt.Format(time.RFC3339)
	}
	if status.ExpiresAt != nil {
		m["expiresAt"] = status.ExpiresAt.Format(time.RFC3339)
	}
	return m
}

func StatusFromMap(m map[string]any) agentv1.AgentSessionStatus {
	return agentv1.AgentSessionStatus{
		Phase:         stringValue(m["phase"]),
		Reason:        stringValue(m["reason"]),
		Message:       stringValue(m["message"]),
		PodName:       stringValue(m["podName"]),
		ContainerName: defaultString(stringValue(m["containerName"]), agentv1.ContainerName),
		TerminalReady: boolValue(m["terminalReady"]),
		CreatedAt:     parseTimePtr(stringValue(m["createdAt"])),
		ExpiresAt:     parseTimePtr(stringValue(m["expiresAt"])),
	}
}

func Resource(resource string) schema.GroupVersionResource {
	return schema.GroupVersionResource{Group: agentv1.GroupName, Version: agentv1.Version, Resource: resource}
}

func stringMapToInterface(in map[string]string) map[string]any {
	out := map[string]any{}
	for k, v := range in {
		out[k] = v
	}
	return out
}

func stringValue(v any) string {
	s, _ := v.(string)
	return s
}

func int64Value(v any) int64 {
	switch n := v.(type) {
	case int64:
		return n
	case int:
		return int64(n)
	case float64:
		return int64(n)
	default:
		return 0
	}
}

func boolValue(v any) bool {
	b, _ := v.(bool)
	return b
}

func defaultString(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}

func parseTimePtr(s string) *metav1.Time {
	if s == "" {
		return nil
	}
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return nil
	}
	mt := metav1.NewTime(t)
	return &mt
}

func IsNotFound(err error) bool {
	return stringsContains(fmt.Sprint(err), "not found")
}

func stringsContains(s, substr string) bool { return strings.Contains(s, substr) }
