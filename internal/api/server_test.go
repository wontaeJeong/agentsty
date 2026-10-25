package api

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"agentcask/internal/auth"
	"agentcask/internal/redact"
	"agentcask/internal/terminal"
	"agentcask/internal/testutil/oidctest"
	"github.com/gorilla/websocket"
)

// A missing authenticator must never silently activate development identity.
func TestUnconfiguredServerRejectsArbitraryBearer(t *testing.T) {
	server := (&Server{Store: NewMemoryStore(false)}).Handler()
	for _, token := range []string{"anything", "dev-token", "user:alice"} {
		r := httptest.NewRequest(http.MethodGet, "/api/v1/sessions", nil)
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, r)
		if w.Code != http.StatusUnauthorized {
			t.Errorf("unverified token accepted: status=%d", w.Code)
		}
	}
}

func TestCreateSessionSuccessHidesInternals(t *testing.T) {
	s, p := authenticatedServer(t, NewMemoryStore(true))
	server := httptest.NewServer(s.Handler())
	defer server.Close()
	body := `{"tool":"opencode","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`
	req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+p.Token(t, "alice", nil))
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
	s, p := authenticatedServer(t, NewMemoryStore(false))
	server := httptest.NewServer(s.Handler())
	defer server.Close()
	for _, body := range []string{
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200,"runtimeClassName":"kata"}`,
		`{"tool":"stub","repoUrl":"REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://user:password@example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"sk-credential-looking-value","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`,
		`{"tool":"stub","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"raw","ttlSeconds":7200}`,
	} {
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(body))
		req.Header.Set("Authorization", "Bearer "+p.Token(t, "alice", nil))
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
	s, p := authenticatedServer(t, store)
	server := httptest.NewServer(s.Handler())
	defer server.Close()
	create := func(token string) {
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/sessions", strings.NewReader(`{"tool":"opencode","repoUrl":"https://example.invalid/repo.git","branch":"main","modelRef":"default","resourceProfile":"small","isolationProfile":"default","ttlSeconds":7200}`))
		req.Header.Set("Authorization", "Bearer "+token)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
	}
	create(p.Token(t, "alice", nil))
	create(p.Token(t, "bob", nil))
	req, _ := http.NewRequest(http.MethodGet, server.URL+"/api/v1/sessions", nil)
	req.Header.Set("Authorization", "Bearer "+p.Token(t, "alice", nil))
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

func authenticatedServer(t *testing.T, store Store) (*Server, *oidctest.Provider) {
	t.Helper()
	p := oidctest.New(t)
	v, err := auth.NewOIDC(context.Background(), auth.Config{Issuer: p.Server.URL, Audience: "cask-api", JWKSURL: p.Server.URL + "/keys", HTTPClient: p.Server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	return &Server{Store: store, Namespace: "agentcask-sessions", Authenticator: v, Audit: slog.New(slog.NewJSONHandler(io.Discard, nil)), Terminal: &terminal.Gateway{Resolver: store, Backend: terminal.EchoBackend{}}}, p
}

func TestVerifiedIdentityOwnsSessionsAndDeniesCrossUserAccess(t *testing.T) {
	s, p := authenticatedServer(t, NewMemoryStore(true))
	var audit bytes.Buffer
	s.Audit = slog.New(slog.NewJSONHandler(&audit, nil))
	h := s.Handler()
	request := func(method, path, token, body string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w
	}
	alice := p.Token(t, "alice", nil)
	bob := p.Token(t, "bob", nil)
	w := request("POST", "/api/v1/sessions", alice, `{"tool":"opencode","repoUrl":"https://example.invalid/repo.git"}`)
	if w.Code != 201 {
		t.Fatalf("create: %d %s", w.Code, w.Body)
	}
	var session SessionResponse
	if err := json.Unmarshal(w.Body.Bytes(), &session); err != nil {
		t.Fatal(err)
	}
	stored, err := s.Store.Get(context.Background(), session.ID)
	if err != nil || stored.Spec.UserID == "alice" || stored.Spec.UserID == "dev-user" {
		t.Fatal("unverified owner stored")
	}
	for _, test := range []struct{ method, path string }{
		{"GET", "/api/v1/sessions/" + session.ID}, {"DELETE", "/api/v1/sessions/" + session.ID}, {"GET", "/api/v1/sessions/" + session.ID + "/terminal"},
	} {
		if got := request(test.method, test.path, bob, ""); got.Code != 403 {
			t.Fatalf("cross-user %s: %d", test.method, got.Code)
		}
	}
	for _, token := range []string{"random", "user:alice", "dev-token", p.Token(t, "alice", map[string]any{"exp": time.Now().Add(-time.Minute).Unix()})} {
		if got := request("GET", "/api/v1/sessions", token, ""); got.Code != 401 || !strings.HasPrefix(got.Header().Get("WWW-Authenticate"), "Bearer") {
			t.Fatalf("invalid credential: status=%d", got.Code)
		}
	}
	if got := request("GET", "/api/v1/sessions", p.Token(t, "alice", map[string]any{"scope": "other"}), ""); got.Code != 403 {
		t.Fatalf("missing permission: %d", got.Code)
	}
	if got := request("GET", "/api/v1/sessions/"+session.ID, alice, ""); got.Code != 200 {
		t.Fatalf("owner denied: %d", got.Code)
	}
	if got := request("DELETE", "/api/v1/sessions/"+session.ID, alice, ""); got.Code != 200 {
		t.Fatalf("owner delete denied: %d", got.Code)
	}
	if strings.Contains(audit.String(), alice) || strings.Contains(audit.String(), bob) || strings.Contains(audit.String(), "user:alice") {
		t.Fatal("credential leaked in audit")
	}
	for _, event := range []string{"authentication.succeeded", "authentication.failed", "authorization.denied", "authorization.allowed"} {
		if !strings.Contains(audit.String(), event) {
			t.Errorf("missing audit event %s", event)
		}
	}
}

func TestDuplicateAuthorizationRejected(t *testing.T) {
	s, p := authenticatedServer(t, NewMemoryStore(false))
	r := httptest.NewRequest("GET", "/api/v1/sessions", nil)
	r.Header.Add("Authorization", "Bearer "+p.Token(t, "alice", nil))
	r.Header.Add("Authorization", "Bearer "+p.Token(t, "bob", nil))
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 401 {
		t.Fatalf("ambiguous authorization accepted: %d", w.Code)
	}
}

type denyPolicy struct{}

func (denyPolicy) Allow(context.Context, auth.Identity, string, string) bool { return false }

type createTrackingStore struct {
	Store
	creates int
}

func (s *createTrackingStore) Create(ctx context.Context, session *agentv1.AgentSession) (*agentv1.AgentSession, error) {
	s.creates++
	return s.Store.Create(ctx, session)
}

func TestCreationConsultsAdditionalPolicyBeforePersistence(t *testing.T) {
	store := &createTrackingStore{Store: NewMemoryStore(false)}
	s, p := authenticatedServer(t, store)
	s.Authorizer = denyPolicy{}
	var audit bytes.Buffer
	s.Audit = slog.New(slog.NewJSONHandler(&audit, nil))
	r := httptest.NewRequest("POST", "/api/v1/sessions", strings.NewReader(`{"tool":"opencode","repoUrl":"https://example.invalid/repo.git"}`))
	r.Header.Set("Authorization", "Bearer "+p.Token(t, "alice", nil))
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 403 || store.creates != 0 {
		t.Fatalf("create bypassed policy: status=%d persisted=%d", w.Code, store.creates)
	}
	if !strings.Contains(audit.String(), "authorization.denied") || strings.Contains(audit.String(), "authorization.allowed") {
		t.Fatal("denied creation recorded as allowed")
	}
}

func TestTerminalClosesAtJWTExpiryAndRejectsUntrustedOrigin(t *testing.T) {
	s, p := authenticatedServer(t, NewMemoryStore(true))
	server := httptest.NewServer(s.Handler())
	defer server.Close()
	// Create with a long-lived token; terminal authentication has its own lifetime.
	r, _ := http.NewRequest("POST", server.URL+"/api/v1/sessions", strings.NewReader(`{"tool":"stub","repoUrl":"https://example.invalid/repo.git"}`))
	r.Header.Set("Authorization", "Bearer "+p.Token(t, "alice", nil))
	resp, err := http.DefaultClient.Do(r)
	if err != nil {
		t.Fatal(err)
	}
	var session SessionResponse
	err = json.NewDecoder(resp.Body).Decode(&session)
	resp.Body.Close()
	if err != nil || resp.StatusCode != 201 {
		t.Fatalf("create: %v %d", err, resp.StatusCode)
	}
	url := "ws" + strings.TrimPrefix(server.URL, "http") + "/api/v1/sessions/" + session.ID + "/terminal"
	headers := http.Header{"Authorization": []string{"Bearer " + p.Token(t, "alice", nil)}, "Origin": []string{"https://untrusted.invalid"}}
	c, denied, err := websocket.DefaultDialer.Dial(url, headers)
	if c != nil {
		c.Close()
	}
	if denied != nil {
		denied.Body.Close()
	}
	if err == nil || denied == nil || denied.StatusCode != 403 {
		t.Error("cross-origin terminal accepted")
	}
	headers.Del("Origin")
	headers.Set("Authorization", "Bearer "+p.Token(t, "alice", map[string]any{"exp": time.Now().Add(2 * time.Second).Unix()}))
	c, _, err = websocket.DefaultDialer.Dial(url, headers)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	_ = c.SetReadDeadline(time.Now().Add(5 * time.Second))
	_, _, err = c.ReadMessage()
	if err != nil {
		t.Fatalf("initial terminal output: %v", err)
	}
	_, _, err = c.ReadMessage()
	if err == nil {
		t.Fatal("terminal remained open")
	}
	if nerr, ok := err.(net.Error); ok && nerr.Timeout() {
		t.Fatal("terminal not closed at JWT expiry")
	}
}
