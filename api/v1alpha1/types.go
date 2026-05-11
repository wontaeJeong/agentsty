package v1alpha1

import (
	"fmt"
	"strings"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

const (
	GroupName = "agentcask.aidev.samsungds.net"
	Version   = "v1alpha1"
	Kind      = "AgentSession"
	Resource  = "agentsessions"

	Finalizer = GroupName + "/finalizer"

	LabelSessionID = GroupName + "/session-id"
	LabelUserID    = GroupName + "/user-id"
	LabelComponent = GroupName + "/component"

	ContainerName = "agent"

	PhasePending      = "Pending"
	PhaseProvisioning = "Provisioning"
	PhaseRunning      = "Running"
	PhaseFailed       = "Failed"
	PhaseTerminating  = "Terminating"
	PhaseExpired      = "Expired"
	PhaseSucceeded    = "Succeeded"

	ReasonUnsupportedTool             = "UnsupportedTool"
	ReasonUnsupportedIsolationProfile = "UnsupportedIsolationProfile"
	ReasonRuntimeClassNotFound        = "RuntimeClassNotFound"
	ReasonPodCreateFailed             = "PodCreateFailed"
	ReasonPodUnschedulable            = "PodUnschedulable"
	ReasonTerminalNotReady            = "TerminalNotReady"
	ReasonExpired                     = "Expired"
)

var (
	GroupVersion = schema.GroupVersion{Group: GroupName, Version: Version}
	GVR          = schema.GroupVersionResource{Group: GroupName, Version: Version, Resource: Resource}
	GVK          = schema.GroupVersionKind{Group: GroupName, Version: Version, Kind: Kind}

	AllowedTools = map[string]struct{}{
		"opencode":    {},
		"claude-code": {},
		"codex":       {},
		"openclaw":    {},
		"hermes":      {},
		"stub":        {},
	}

	AllowedModelRefs = map[string]struct{}{
		"default": {},
	}

	AllowedResourceProfiles = map[string]struct{}{
		"small":  {},
		"medium": {},
		"large":  {},
	}

	AllowedIsolationProfiles = map[string]struct{}{
		"default": {},
		"kata":    {},
	}
)

type AgentSession struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata"`
	Spec              AgentSessionSpec   `json:"spec"`
	Status            AgentSessionStatus `json:"status"`
}

type AgentSessionSpec struct {
	UserID          string        `json:"userId"`
	Tool            string        `json:"tool"`
	Repo            RepoSpec      `json:"repo"`
	ModelRef        string        `json:"modelRef"`
	ResourceProfile string        `json:"resourceProfile"`
	Isolation       IsolationSpec `json:"isolation"`
	TTLSeconds      int64         `json:"ttlSeconds"`
}

type RepoSpec struct {
	URL    string `json:"url"`
	Branch string `json:"branch"`
}

type IsolationSpec struct {
	Profile string `json:"profile"`
}

type AgentSessionStatus struct {
	Phase         string       `json:"phase,omitempty"`
	Reason        string       `json:"reason,omitempty"`
	Message       string       `json:"message,omitempty"`
	PodName       string       `json:"podName,omitempty"`
	ContainerName string       `json:"containerName,omitempty"`
	TerminalReady bool         `json:"terminalReady,omitempty"`
	CreatedAt     *metav1.Time `json:"createdAt,omitempty"`
	ExpiresAt     *metav1.Time `json:"expiresAt,omitempty"`
}

func NewAgentSession(name, namespace string, spec AgentSessionSpec, now metav1.Time) *AgentSession {
	expires := metav1.NewTime(now.Time.Add(time.Duration(spec.TTLSeconds) * time.Second))
	return &AgentSession{
		TypeMeta: metav1.TypeMeta{APIVersion: GroupVersion.String(), Kind: Kind},
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
			Labels: map[string]string{
				LabelSessionID: name,
				LabelUserID:    spec.UserID,
			},
		},
		Spec: spec,
		Status: AgentSessionStatus{
			Phase:         PhasePending,
			ContainerName: ContainerName,
			CreatedAt:     &now,
			ExpiresAt:     &expires,
		},
	}
}

func (s AgentSessionSpec) Validate() error {
	if strings.TrimSpace(s.UserID) == "" {
		return fmt.Errorf("userId is required")
	}
	if _, ok := AllowedTools[s.Tool]; !ok {
		return fmt.Errorf("unsupported tool %q", s.Tool)
	}
	if _, ok := AllowedModelRefs[s.ModelRef]; !ok {
		return fmt.Errorf("unsupported modelRef %q", s.ModelRef)
	}
	if _, ok := AllowedResourceProfiles[s.ResourceProfile]; !ok {
		return fmt.Errorf("unsupported resourceProfile %q", s.ResourceProfile)
	}
	if _, ok := AllowedIsolationProfiles[s.Isolation.Profile]; !ok {
		return fmt.Errorf("unsupported isolationProfile %q", s.Isolation.Profile)
	}
	if s.TTLSeconds <= 0 || s.TTLSeconds > 24*60*60 {
		return fmt.Errorf("ttlSeconds must be between 1 and 86400")
	}
	return nil
}
