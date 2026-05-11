package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"agentcask/internal/redact"
	"agentcask/internal/terminal"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type Store interface {
	Ready(ctx context.Context) error
	Create(ctx context.Context, session *agentv1.AgentSession) (*agentv1.AgentSession, error)
	List(ctx context.Context, userID string) ([]agentv1.AgentSession, error)
	Get(ctx context.Context, id string) (*agentv1.AgentSession, error)
	Delete(ctx context.Context, id string) error
}

type Server struct {
	Store     Store
	Terminal  *terminal.Gateway
	Namespace string
	Now       func() time.Time
}

type CreateSessionRequest struct {
	Tool             string `json:"tool"`
	RepoURL          string `json:"repoUrl"`
	Branch           string `json:"branch"`
	ModelRef         string `json:"modelRef"`
	ResourceProfile  string `json:"resourceProfile"`
	IsolationProfile string `json:"isolationProfile"`
	TTLSeconds       int64  `json:"ttlSeconds"`
}

type SessionResponse struct {
	ID               string `json:"id"`
	Phase            string `json:"phase"`
	Reason           string `json:"reason,omitempty"`
	Message          string `json:"message,omitempty"`
	Tool             string `json:"tool"`
	ModelRef         string `json:"modelRef"`
	ResourceProfile  string `json:"resourceProfile"`
	IsolationProfile string `json:"isolationProfile"`
	TerminalReady    bool   `json:"terminalReady,omitempty"`
	CreatedAt        string `json:"createdAt,omitempty"`
	ExpiresAt        string `json:"expiresAt,omitempty"`
	TerminalURL      string `json:"terminalUrl,omitempty"`
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", s.healthz)
	mux.HandleFunc("/readyz", s.readyz)
	mux.HandleFunc("/api/v1/sessions", s.sessions)
	mux.HandleFunc("/api/v1/sessions/", s.sessionByID)
	return redactMiddleware(mux)
}

func (s *Server) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) readyz(w http.ResponseWriter, r *http.Request) {
	if s.Store == nil {
		http.Error(w, "store not configured", http.StatusServiceUnavailable)
		return
	}
	if err := s.Store.Ready(r.Context()); err != nil {
		http.Error(w, "not ready", http.StatusServiceUnavailable)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) sessions(w http.ResponseWriter, r *http.Request) {
	userID, ok := userFromRequest(r)
	if !ok {
		http.Error(w, "not authenticated", http.StatusUnauthorized)
		return
	}
	switch r.Method {
	case http.MethodPost:
		s.createSession(w, r, userID)
	case http.MethodGet:
		s.listSessions(w, r, userID)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *Server) sessionByID(w http.ResponseWriter, r *http.Request) {
	userID, ok := userFromRequest(r)
	if !ok {
		http.Error(w, "not authenticated", http.StatusUnauthorized)
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/sessions/")
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) == 0 || parts[0] == "" {
		http.NotFound(w, r)
		return
	}
	id := parts[0]
	if len(parts) == 2 && parts[1] == "terminal" {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if s.Terminal == nil {
			http.Error(w, "terminal gateway not configured", http.StatusServiceUnavailable)
			return
		}
		s.Terminal.Serve(w, r, userID, id)
		return
	}
	if len(parts) != 1 {
		http.NotFound(w, r)
		return
	}
	switch r.Method {
	case http.MethodGet:
		s.getSession(w, r, userID, id)
	case http.MethodDelete:
		s.deleteSession(w, r, userID, id)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *Server) createSession(w http.ResponseWriter, r *http.Request, userID string) {
	var raw map[string]any
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&raw); err != nil {
		http.Error(w, "invalid json", http.StatusBadRequest)
		return
	}
	if err := rejectForbidden(raw); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	req := CreateSessionRequest{
		Tool:             stringValue(raw["tool"]),
		RepoURL:          stringValue(raw["repoUrl"]),
		Branch:           defaultString(stringValue(raw["branch"]), "main"),
		ModelRef:         defaultString(stringValue(raw["modelRef"]), "default"),
		ResourceProfile:  defaultString(stringValue(raw["resourceProfile"]), "small"),
		IsolationProfile: defaultString(stringValue(raw["isolationProfile"]), "default"),
		TTLSeconds:       int64Value(raw["ttlSeconds"]),
	}
	if req.TTLSeconds == 0 {
		req.TTLSeconds = int64((2 * time.Hour).Seconds())
	}
	now := metav1.NewTime(s.now())
	spec := agentv1.AgentSessionSpec{
		UserID:          userID,
		Tool:            req.Tool,
		Repo:            agentv1.RepoSpec{URL: req.RepoURL, Branch: req.Branch},
		ModelRef:        req.ModelRef,
		ResourceProfile: req.ResourceProfile,
		Isolation:       agentv1.IsolationSpec{Profile: req.IsolationProfile},
		TTLSeconds:      req.TTLSeconds,
	}
	if err := spec.Validate(); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	session := agentv1.NewAgentSession(generateSessionID(), defaultString(s.Namespace, "agentcask-sessions"), spec, now)
	created, err := s.Store.Create(r.Context(), session)
	if err != nil {
		http.Error(w, redact.String(err.Error()), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusCreated, responseFromSession(created, true))
}

func (s *Server) listSessions(w http.ResponseWriter, r *http.Request, userID string) {
	sessions, err := s.Store.List(r.Context(), userID)
	if err != nil {
		http.Error(w, redact.String(err.Error()), http.StatusInternalServerError)
		return
	}
	sort.Slice(sessions, func(i, j int) bool { return sessions[i].Name < sessions[j].Name })
	items := make([]SessionResponse, 0, len(sessions))
	for i := range sessions {
		items = append(items, responseFromSession(&sessions[i], false))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) getSession(w http.ResponseWriter, r *http.Request, userID, id string) {
	session, err := s.Store.Get(r.Context(), id)
	if err != nil {
		http.Error(w, "session not found", http.StatusNotFound)
		return
	}
	if session.Spec.UserID != userID {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	writeJSON(w, http.StatusOK, responseFromSession(session, false))
}

func (s *Server) deleteSession(w http.ResponseWriter, r *http.Request, userID, id string) {
	session, err := s.Store.Get(r.Context(), id)
	if err != nil {
		http.Error(w, "session not found", http.StatusNotFound)
		return
	}
	if session.Spec.UserID != userID {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	if err := s.Store.Delete(r.Context(), id); err != nil {
		http.Error(w, redact.String(err.Error()), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "deleted": true})
}

func userFromRequest(r *http.Request) (string, bool) {
	header := r.Header.Get("Authorization")
	if !strings.HasPrefix(header, "Bearer ") {
		return "", false
	}
	token := strings.TrimSpace(strings.TrimPrefix(header, "Bearer "))
	if token == "" {
		return "", false
	}
	if strings.HasPrefix(token, "user:") && strings.TrimPrefix(token, "user:") != "" {
		return strings.TrimPrefix(token, "user:"), true
	}
	return "dev-user", true
}

func responseFromSession(session *agentv1.AgentSession, includeTerminalURL bool) SessionResponse {
	resp := SessionResponse{
		ID:               session.Name,
		Phase:            defaultString(session.Status.Phase, agentv1.PhasePending),
		Reason:           session.Status.Reason,
		Message:          session.Status.Message,
		Tool:             session.Spec.Tool,
		ModelRef:         session.Spec.ModelRef,
		ResourceProfile:  session.Spec.ResourceProfile,
		IsolationProfile: session.Spec.Isolation.Profile,
		TerminalReady:    session.Status.TerminalReady,
	}
	if session.Status.CreatedAt != nil {
		resp.CreatedAt = session.Status.CreatedAt.Format(time.RFC3339)
	}
	if session.Status.ExpiresAt != nil {
		resp.ExpiresAt = session.Status.ExpiresAt.Format(time.RFC3339)
	}
	if includeTerminalURL {
		resp.TerminalURL = "/api/v1/sessions/" + session.Name + "/terminal"
	}
	return resp
}

func rejectForbidden(raw map[string]any) error {
	allowed := map[string]struct{}{"tool": {}, "repoUrl": {}, "branch": {}, "modelRef": {}, "resourceProfile": {}, "isolationProfile": {}, "ttlSeconds": {}}
	for key, value := range raw {
		if _, ok := allowed[key]; !ok {
			return fmt.Errorf("unsupported field %q", key)
		}
		if redact.ContainsSecretLikeKey(key) {
			return fmt.Errorf("forbidden field %q", key)
		}
		if containsSecretValue(value) {
			return errors.New("request contains forbidden secret-looking value")
		}
	}
	return nil
}

func containsSecretValue(v any) bool {
	s, ok := v.(string)
	if !ok {
		return false
	}
	if strings.Contains(s, redact.Sentinel) {
		return true
	}
	if parsed, err := url.Parse(s); err == nil && parsed.User != nil {
		return true
	}
	lower := strings.ToLower(s)
	for _, marker := range []string{"sk-", "ghp_", "github_pat_", "glpat-", "xoxb-", "akia", "anthropic_api_key"} {
		if strings.Contains(lower, marker) {
			return true
		}
	}
	return false
}

func generateSessionID() string {
	buf := make([]byte, 4)
	if _, err := rand.Read(buf); err != nil {
		return fmt.Sprintf("sess-%d", time.Now().UnixNano())
	}
	return "sess-" + hex.EncodeToString(buf)
}

func (s *Server) now() time.Time {
	if s.Now != nil {
		return s.Now()
	}
	return time.Now().UTC()
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func redactMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		next.ServeHTTP(w, r)
	})
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

func defaultString(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}
