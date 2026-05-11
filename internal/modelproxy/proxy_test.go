package modelproxy

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"agentcask/internal/redact"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type resolverFunc func(context.Context, string) (*agentv1.AgentSession, error)

func (f resolverFunc) Get(ctx context.Context, id string) (*agentv1.AgentSession, error) {
	return f(ctx, id)
}

func TestModelProxyTokenValidation(t *testing.T) {
	tokens := TokenManager{Secret: "test-secret"}
	proxy := &Proxy{Tokens: tokens, UpstreamKey: redact.Sentinel}
	server := httptest.NewServer(http.HandlerFunc(proxy.Handler))
	defer server.Close()

	req, _ := http.NewRequest(http.MethodPost, server.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+tokens.Generate("sess-test"))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("valid token got status %d", resp.StatusCode)
	}

	req, _ = http.NewRequest(http.MethodPost, server.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer invalid")
	resp, err = http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("invalid token got status %d", resp.StatusCode)
	}
}

func TestModelProxyDoesNotExposeUpstreamKey(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+redact.Sentinel {
			t.Fatalf("upstream did not receive server-side key")
		}
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer upstream.Close()
	tokens := TokenManager{Secret: "test-secret"}
	proxy := httptest.NewServer(http.HandlerFunc((&Proxy{Tokens: tokens, UpstreamURL: upstream.URL, UpstreamKey: redact.Sentinel}).Handler))
	defer proxy.Close()
	req, _ := http.NewRequest(http.MethodPost, proxy.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+tokens.Generate("sess-test"))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if strings.Contains(string(body), redact.Sentinel) {
		t.Fatalf("response leaked upstream key: %s", string(body))
	}
}

func TestModelProxyRejectsExpiredToken(t *testing.T) {
	now := time.Date(2026, 5, 12, 0, 0, 0, 0, time.UTC)
	tokens := TokenManager{Secret: "test-secret", Now: func() time.Time { return now }}
	token := tokens.GenerateUntil("sess-test", now.Add(-time.Minute))
	proxy := httptest.NewServer(http.HandlerFunc((&Proxy{Tokens: tokens}).Handler))
	defer proxy.Close()
	req, _ := http.NewRequest(http.MethodPost, proxy.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expired token got status %d", resp.StatusCode)
	}
}

func TestModelProxyRejectsDeletedSessionToken(t *testing.T) {
	now := time.Date(2026, 5, 12, 0, 0, 0, 0, time.UTC)
	tokens := TokenManager{Secret: "test-secret", Now: func() time.Time { return now }}
	expires := metav1.NewTime(now.Add(time.Hour))
	proxy := httptest.NewServer(http.HandlerFunc((&Proxy{
		Tokens: tokens,
		Sessions: resolverFunc(func(context.Context, string) (*agentv1.AgentSession, error) {
			return &agentv1.AgentSession{Spec: agentv1.AgentSessionSpec{ModelRef: "default"}, Status: agentv1.AgentSessionStatus{Phase: agentv1.PhaseExpired, ExpiresAt: &expires}}, nil
		}),
	}).Handler))
	defer proxy.Close()
	req, _ := http.NewRequest(http.MethodPost, proxy.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+tokens.GenerateUntil("sess-test", now.Add(time.Hour)))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expired session token got status %d", resp.StatusCode)
	}
}

func TestModelProxyRejectsDeletingSessionToken(t *testing.T) {
	now := time.Date(2026, 5, 12, 0, 0, 0, 0, time.UTC)
	tokens := TokenManager{Secret: "test-secret", Now: func() time.Time { return now }}
	deletingAt := metav1.NewTime(now)
	expires := metav1.NewTime(now.Add(time.Hour))
	proxy := httptest.NewServer(http.HandlerFunc((&Proxy{
		Tokens: tokens,
		Sessions: resolverFunc(func(context.Context, string) (*agentv1.AgentSession, error) {
			return &agentv1.AgentSession{
				ObjectMeta: metav1.ObjectMeta{DeletionTimestamp: &deletingAt},
				Spec:       agentv1.AgentSessionSpec{ModelRef: "default"},
				Status:     agentv1.AgentSessionStatus{Phase: agentv1.PhaseRunning, ExpiresAt: &expires},
			}, nil
		}),
	}).Handler))
	defer proxy.Close()
	req, _ := http.NewRequest(http.MethodPost, proxy.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+tokens.GenerateUntil("sess-test", now.Add(time.Hour)))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("deleting session token got status %d", resp.StatusCode)
	}
}

func TestModelProxyRejectsUnsupportedModelRef(t *testing.T) {
	now := time.Date(2026, 5, 12, 0, 0, 0, 0, time.UTC)
	tokens := TokenManager{Secret: "test-secret", Now: func() time.Time { return now }}
	expires := metav1.NewTime(now.Add(time.Hour))
	proxy := httptest.NewServer(http.HandlerFunc((&Proxy{
		Tokens: tokens,
		Sessions: resolverFunc(func(context.Context, string) (*agentv1.AgentSession, error) {
			return &agentv1.AgentSession{
				Spec:   agentv1.AgentSessionSpec{ModelRef: "unsupported"},
				Status: agentv1.AgentSessionStatus{Phase: agentv1.PhaseRunning, ExpiresAt: &expires},
			}, nil
		}),
	}).Handler))
	defer proxy.Close()
	req, _ := http.NewRequest(http.MethodPost, proxy.URL, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+tokens.GenerateUntil("sess-test", now.Add(time.Hour)))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("unsupported modelRef token got status %d", resp.StatusCode)
	}
}
