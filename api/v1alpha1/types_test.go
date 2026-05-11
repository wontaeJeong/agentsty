package v1alpha1

import (
	"encoding/json"
	"strings"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func TestAgentSessionSpecValidation(t *testing.T) {
	spec := AgentSessionSpec{UserID: "dev-user", Tool: "stub", Repo: RepoSpec{URL: "https://example.invalid/repo.git", Branch: "main"}, ModelRef: "default", ResourceProfile: "small", Isolation: IsolationSpec{Profile: "default"}, TTLSeconds: 7200}
	if err := spec.Validate(); err != nil {
		t.Fatalf("valid spec rejected: %v", err)
	}
	spec.Isolation.Profile = "runtimeclass/kata"
	if err := spec.Validate(); err == nil {
		t.Fatal("unsupported isolation profile accepted")
	}
}

func TestAgentSessionJSONContainsNoSecretFields(t *testing.T) {
	session := NewAgentSession("sess-test", "agentcask-sessions", AgentSessionSpec{UserID: "dev-user", Tool: "stub", Repo: RepoSpec{URL: "https://example.invalid/repo.git", Branch: "main"}, ModelRef: "default", ResourceProfile: "small", Isolation: IsolationSpec{Profile: "default"}, TTLSeconds: 7200}, metav1.Now())
	data, err := json.Marshal(session)
	if err != nil {
		t.Fatal(err)
	}
	lower := strings.ToLower(string(data))
	for _, forbidden := range []string{"apikey", "api_key", "password", "secret", "runtimeclassname", "real_upstream_key_should_never_leak"} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("AgentSession JSON contains forbidden fragment %q: %s", forbidden, data)
		}
	}
}
