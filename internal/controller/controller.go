package controller

import (
	"context"
	"fmt"
	"slices"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"agentcask/internal/isolation"
	"agentcask/internal/kube"
	"agentcask/internal/modelproxy"
	"agentcask/internal/redact"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
)

type Config struct {
	Namespace         string
	RuntimeImage      string
	ModelProxyURL     string
	TokenSecret       string
	Profiles          isolation.Profiles
	ReconcileInterval time.Duration
}

type Reconciler struct {
	Dynamic dynamic.Interface
	Kube    kubernetes.Interface
	Config  Config
	Now     func() time.Time
}

func DefaultConfig() Config {
	return Config{
		Namespace:         kube.DefaultSessionNamespace,
		RuntimeImage:      "agentcask/agent-runtime:dev",
		ModelProxyURL:     "http://cask-model-proxy.agentcask-system.svc.cluster.local:8080/internal/model-proxy/v1",
		TokenSecret:       "dev-session-proxy-secret",
		Profiles:          isolation.DefaultProfiles(),
		ReconcileInterval: 2 * time.Second,
	}
}

func (r *Reconciler) Run(ctx context.Context) error {
	if r.Dynamic == nil || r.Kube == nil {
		return fmt.Errorf("kubernetes clients are required")
	}
	interval := r.config().ReconcileInterval
	if interval <= 0 {
		interval = 2 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if err := r.reconcileAll(ctx); err != nil {
			fmt.Printf("controller reconcile error: %s\n", redact.String(err.Error()))
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *Reconciler) reconcileAll(ctx context.Context) error {
	items, err := r.Dynamic.Resource(agentv1.GVR).Namespace(r.namespace()).List(ctx, metav1.ListOptions{})
	if err != nil {
		return err
	}
	for i := range items.Items {
		if err := r.Reconcile(ctx, items.Items[i].GetName()); err != nil {
			fmt.Printf("reconcile %s failed: %s\n", items.Items[i].GetName(), redact.String(err.Error()))
		}
	}
	return nil
}

func (r *Reconciler) Reconcile(ctx context.Context, name string) error {
	res := r.Dynamic.Resource(agentv1.GVR).Namespace(r.namespace())
	u, err := res.Get(ctx, name, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	if err != nil {
		return err
	}
	session, err := kube.FromUnstructured(u)
	if err != nil {
		return err
	}
	if session.DeletionTimestamp != nil {
		return r.cleanup(ctx, session)
	}
	if !hasFinalizer(session.Finalizers, agentv1.Finalizer) {
		finalizers := append(session.Finalizers, agentv1.Finalizer)
		if err := (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchFinalizers(ctx, session.Name, finalizers); err != nil {
			return err
		}
	}
	if expired(session, r.now()) {
		_ = r.deletePod(ctx, session.Name)
		status := session.Status
		status.Phase = agentv1.PhaseExpired
		status.Reason = agentv1.ReasonExpired
		status.Message = "session ttl expired"
		status.TerminalReady = false
		ensureStatusTimes(session, &status, r.now())
		return (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchStatus(ctx, session.Name, status)
	}
	profile, err := r.config().Profiles.Resolve(session.Spec.Isolation.Profile)
	if err != nil {
		return r.fail(ctx, session, agentv1.ReasonUnsupportedIsolationProfile, err.Error())
	}
	if err := isolation.CheckRuntimeClass(ctx, r.Kube, profile); err != nil {
		return r.fail(ctx, session, agentv1.ReasonRuntimeClassNotFound, err.Error())
	}
	podName := PodName(session.Name)
	pod, err := r.Kube.CoreV1().Pods(r.namespace()).Get(ctx, podName, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		pod = BuildPod(session, r.config(), profile)
		if _, err := r.Kube.CoreV1().Pods(r.namespace()).Create(ctx, pod, metav1.CreateOptions{}); err != nil {
			return r.fail(ctx, session, agentv1.ReasonPodCreateFailed, err.Error())
		}
		status := session.Status
		status.Phase = agentv1.PhaseProvisioning
		status.PodName = podName
		status.ContainerName = agentv1.ContainerName
		status.TerminalReady = false
		ensureStatusTimes(session, &status, r.now())
		return (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchStatus(ctx, session.Name, status)
	}
	if err != nil {
		return err
	}
	status := session.Status
	status.PodName = podName
	status.ContainerName = agentv1.ContainerName
	if pod.Status.Phase == corev1.PodRunning || pod.Status.Phase == corev1.PodSucceeded {
		status.Phase = agentv1.PhaseRunning
		status.TerminalReady = true
	} else {
		status.Phase = agentv1.PhaseProvisioning
		status.TerminalReady = false
	}
	ensureStatusTimes(session, &status, r.now())
	return (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchStatus(ctx, session.Name, status)
}

func BuildPod(session *agentv1.AgentSession, cfg Config, profile isolation.Profile) *corev1.Pod {
	if cfg.RuntimeImage == "" {
		cfg.RuntimeImage = DefaultConfig().RuntimeImage
	}
	if cfg.ModelProxyURL == "" {
		cfg.ModelProxyURL = DefaultConfig().ModelProxyURL
	}
	expiresAt := expiryTime(session)
	if expiresAt == nil {
		ttlSeconds := session.Spec.TTLSeconds
		if ttlSeconds <= 0 {
			ttlSeconds = int64(modelproxy.DefaultTokenTTL / time.Second)
		}
		fallback := time.Now().UTC().Add(time.Duration(ttlSeconds) * time.Second)
		expiresAt = &fallback
	}
	token := modelproxy.TokenManager{Secret: cfg.TokenSecret}.GenerateUntil(session.Name, *expiresAt)
	runAsNonRoot := true
	allowPrivilegeEscalation := false
	readOnlyRootFilesystem := false
	runAsUser := int64(65532)
	runAsGroup := int64(65532)
	seccomp := corev1.SeccompProfileTypeRuntimeDefault
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      PodName(session.Name),
			Namespace: session.Namespace,
			Labels: map[string]string{
				agentv1.LabelComponent: "agent-session",
				agentv1.LabelSessionID: session.Name,
				agentv1.LabelUserID:    session.Spec.UserID,
			},
			OwnerReferences: []metav1.OwnerReference{{
				APIVersion: agentv1.GroupVersion.String(),
				Kind:       agentv1.Kind,
				Name:       session.Name,
				UID:        types.UID(session.UID),
			}},
		},
		Spec: corev1.PodSpec{
			RestartPolicy:      corev1.RestartPolicyNever,
			ServiceAccountName: "agent-session",
			Containers: []corev1.Container{{
				Name:            agentv1.ContainerName,
				Image:           cfg.RuntimeImage,
				ImagePullPolicy: corev1.PullIfNotPresent,
				Command:         []string{"/bin/sh", "-lc", "trap : TERM INT; while true; do sleep 3600; done"},
				Stdin:           true,
				TTY:             true,
				Env: []corev1.EnvVar{
					{Name: "CASK_MODEL_BASE_URL", Value: cfg.ModelProxyURL},
					{Name: "CASK_SESSION_TOKEN", Value: token},
					{Name: "OPENAI_BASE_URL", Value: cfg.ModelProxyURL},
					{Name: "ANTHROPIC_BASE_URL", Value: cfg.ModelProxyURL},
					{Name: "OPENAI_API_KEY", Value: token},
					{Name: "ANTHROPIC_API_KEY", Value: token},
				},
				Resources: resourcesFor(session.Spec.ResourceProfile),
				SecurityContext: &corev1.SecurityContext{
					RunAsNonRoot:             &runAsNonRoot,
					RunAsUser:                &runAsUser,
					RunAsGroup:               &runAsGroup,
					AllowPrivilegeEscalation: &allowPrivilegeEscalation,
					ReadOnlyRootFilesystem:   &readOnlyRootFilesystem,
					Capabilities:             &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}},
				},
			}},
			SecurityContext: &corev1.PodSecurityContext{SeccompProfile: &corev1.SeccompProfile{Type: seccomp}},
		},
	}
	isolation.Apply(profile, pod)
	return pod
}

func resourcesFor(profile string) corev1.ResourceRequirements {
	profiles := map[string]corev1.ResourceList{
		"small":  {corev1.ResourceCPU: resource.MustParse("50m"), corev1.ResourceMemory: resource.MustParse("256Mi"), corev1.ResourceEphemeralStorage: resource.MustParse("512Mi")},
		"medium": {corev1.ResourceCPU: resource.MustParse("250m"), corev1.ResourceMemory: resource.MustParse("512Mi"), corev1.ResourceEphemeralStorage: resource.MustParse("1Gi")},
		"large":  {corev1.ResourceCPU: resource.MustParse("500m"), corev1.ResourceMemory: resource.MustParse("1Gi"), corev1.ResourceEphemeralStorage: resource.MustParse("2Gi")},
	}
	limits := profiles[profile]
	if limits == nil {
		limits = profiles["small"]
	}
	return corev1.ResourceRequirements{Requests: limits, Limits: limits}
}

func (r *Reconciler) cleanup(ctx context.Context, session *agentv1.AgentSession) error {
	_ = r.deletePod(ctx, session.Name)
	finalizers := removeFinalizer(session.Finalizers, agentv1.Finalizer)
	return (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchFinalizers(ctx, session.Name, finalizers)
}

func (r *Reconciler) deletePod(ctx context.Context, sessionID string) error {
	err := r.Kube.CoreV1().Pods(r.namespace()).Delete(ctx, PodName(sessionID), metav1.DeleteOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

func (r *Reconciler) fail(ctx context.Context, session *agentv1.AgentSession, reason, message string) error {
	status := session.Status
	status.Phase = agentv1.PhaseFailed
	status.Reason = reason
	status.Message = redact.String(message)
	status.TerminalReady = false
	ensureStatusTimes(session, &status, r.now())
	return (&kube.SessionClient{Dynamic: r.Dynamic, Namespace: r.namespace()}).PatchStatus(ctx, session.Name, status)
}

func PodName(sessionID string) string { return "agent-session-" + sessionID }

func (r *Reconciler) namespace() string {
	return defaultString(r.config().Namespace, kube.DefaultSessionNamespace)
}
func (r *Reconciler) config() Config {
	cfg := DefaultConfig()
	if r.Config.Namespace != "" {
		cfg.Namespace = r.Config.Namespace
	}
	if r.Config.RuntimeImage != "" {
		cfg.RuntimeImage = r.Config.RuntimeImage
	}
	if r.Config.ModelProxyURL != "" {
		cfg.ModelProxyURL = r.Config.ModelProxyURL
	}
	if r.Config.TokenSecret != "" {
		cfg.TokenSecret = r.Config.TokenSecret
	}
	if r.Config.Profiles != nil {
		cfg.Profiles = r.Config.Profiles
	}
	if r.Config.ReconcileInterval != 0 {
		cfg.ReconcileInterval = r.Config.ReconcileInterval
	}
	return cfg
}

func (r *Reconciler) now() time.Time {
	if r.Now != nil {
		return r.Now()
	}
	return time.Now().UTC()
}

func expired(session *agentv1.AgentSession, now time.Time) bool {
	expiresAt := expiryTime(session)
	if expiresAt == nil {
		return false
	}
	return now.After(*expiresAt)
}

func expiryTime(session *agentv1.AgentSession) *time.Time {
	if session.Status.ExpiresAt != nil {
		return &session.Status.ExpiresAt.Time
	}
	if session.CreationTimestamp.IsZero() || session.Spec.TTLSeconds <= 0 {
		return nil
	}
	expires := session.CreationTimestamp.Time.Add(time.Duration(session.Spec.TTLSeconds) * time.Second)
	return &expires
}

func ensureStatusTimes(session *agentv1.AgentSession, status *agentv1.AgentSessionStatus, now time.Time) {
	if status.CreatedAt == nil {
		created := session.CreationTimestamp
		if created.IsZero() {
			created = metav1.NewTime(now)
		}
		status.CreatedAt = &created
	}
	if status.ExpiresAt == nil && session.Spec.TTLSeconds > 0 {
		expires := metav1.NewTime(status.CreatedAt.Time.Add(time.Duration(session.Spec.TTLSeconds) * time.Second))
		status.ExpiresAt = &expires
	}
}

func hasFinalizer(values []string, finalizer string) bool {
	return slices.Contains(values, finalizer)
}

func removeFinalizer(values []string, finalizer string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if value != finalizer {
			out = append(out, value)
		}
	}
	return out
}

func defaultString(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}
