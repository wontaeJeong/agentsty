package modelproxy

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	agentv1 "agentcask/api/v1alpha1"
)

type SessionResolver interface {
	Get(ctx context.Context, id string) (*agentv1.AgentSession, error)
}

type Proxy struct {
	Tokens      TokenManager
	Sessions    SessionResolver
	UpstreamURL string
	UpstreamKey string
	Client      *http.Client
}

func (p *Proxy) Handler(w http.ResponseWriter, r *http.Request) {
	sessionID, ok := p.authenticate(r)
	if !ok {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	if p.UpstreamURL == "" {
		writeJSON(w, http.StatusOK, map[string]string{"ok": "true", "sessionId": sessionID})
		return
	}
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "invalid body", http.StatusBadRequest)
		return
	}
	upstream, err := http.NewRequestWithContext(r.Context(), r.Method, p.UpstreamURL, bytes.NewReader(body))
	if err != nil {
		http.Error(w, "bad upstream", http.StatusBadGateway)
		return
	}
	upstream.Header = r.Header.Clone()
	upstream.Header.Del("Authorization")
	if p.UpstreamKey != "" {
		upstream.Header.Set("Authorization", "Bearer "+p.UpstreamKey)
	}
	client := p.Client
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	resp, err := client.Do(upstream)
	if err != nil {
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	for key, values := range resp.Header {
		if strings.EqualFold(key, "Authorization") || strings.EqualFold(key, "Set-Cookie") {
			continue
		}
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func (p *Proxy) authenticate(r *http.Request) (string, bool) {
	header := r.Header.Get("Authorization")
	if !strings.HasPrefix(header, "Bearer ") {
		return "", false
	}
	sessionID, _, ok := p.Tokens.ValidateWithExpiry(strings.TrimPrefix(header, "Bearer "))
	if !ok {
		return "", false
	}
	if p.Sessions == nil {
		return sessionID, true
	}
	session, err := p.Sessions.Get(r.Context(), sessionID)
	if err != nil || session == nil {
		return "", false
	}
	if session.DeletionTimestamp != nil {
		return "", false
	}
	if session.Status.Phase == agentv1.PhaseExpired || session.Status.Phase == agentv1.PhaseTerminating || session.Status.Phase == agentv1.PhaseFailed {
		return "", false
	}
	if session.Status.ExpiresAt != nil && !p.Tokens.now().Before(session.Status.ExpiresAt.Time) {
		return "", false
	}
	if _, ok := agentv1.AllowedModelRefs[session.Spec.ModelRef]; !ok {
		return "", false
	}
	return sessionID, true
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
