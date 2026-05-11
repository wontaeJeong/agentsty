package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"agentcask/internal/redact"
)

func TestCreateSessionSuccessHidesInternals(t *testing.T) {
	server := httptest.NewServer((&Server{Store: NewMemoryStore(true), Namespace: "agentcask-sessions"}).Handler())
	defer server.Close()
	body := `{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`
	req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer dev-token")
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create status=%d", resp.StatusCode)
	}
	var session SessionResponse
	if err := json.NewDecoder(resp.Body).Decode(&session); err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(session)
	if session.ID == "" || session.Phase == "" || session.TerminalURL == "" {
		t.Fatalf("incomplete response: %+v", session)
	}
	if bytes.Contains(data, []byte("podName")) || bytes.Contains(data, []byte(redact.Sentinel)) {
		t.Fatalf("response leaked internal/secret data: %s", data)
	}
}

func TestServerDoesNotServeModelProxyRoute(t *testing.T) {
	server := httptest.NewServer((&Server{Store: NewMemoryStore(true), Namespace: "agentcask-sessions"}).Handler())
	defer server.Close()
	req, _ := http.NewRequest(http.MethodPost, server.URL+"/internal/model-proxy/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer dev-token")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("cask-api served separated model proxy route with status %d", resp.StatusCode)
	}
}

func TestCreateRejectsRuntimeClassNameAndSecrets(t *testing.T) {
	server := httptest.NewServer((&Server{Store: NewMemoryStore(false), Namespace: "agentcask-sessions"}).Handler())
	defer server.Close()
	for _, body := range []string{
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200,"runtimeClassName":"kata"}`,
		`{"tool":"stub","repoUrl":"REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://user:password@example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"sk-credential-looking-value","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"raw","ttlSeconds":7200}`,
	} {
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(body))
		req.Header.Set("Authorization", "Bearer dev-token")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != http.StatusBadRequest {
			t.Fatalf("body %s got status %d", body, resp.StatusCode)
		}
	}
}

func TestListOnlyOwnedSessions(t *testing.T) {
	store := NewMemoryStore(false)
	server := httptest.NewServer((&Server{Store: store, Namespace: "agentcask-sessions"}).Handler())
	defer server.Close()
	create := func(token string) {
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`))
		req.Header.Set("Authorization", "Bearer "+token)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
	}
	create("user:alice")
	create("user:bob")
	req, _ := http.NewRequest(http.MethodGet, server.URL+"/api/v1/sessions", nil)
	req.Header.Set("Authorization", "Bearer user:alice")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var list struct {
		Items []SessionResponse `json:"items"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&list); err != nil {
		t.Fatal(err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("expected one owned session, got %d", len(list.Items))
	}
}
