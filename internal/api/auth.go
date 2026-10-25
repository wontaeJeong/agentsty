package api

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"agentcask/internal/auth"
)

var defaultAudit = slog.New(slog.NewJSONHandler(os.Stderr, nil))

// Authorizer can impose additional project/organization restrictions. Sharing
// and owner transfer are not implemented: a policy cannot bypass ownership.
type Authorizer interface {
	Allow(context.Context, auth.Identity, string, string) bool
}

func (s *Server) protect(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var id auth.Identity
		err := auth.ErrUnauthenticated
		headers := r.Header.Values("Authorization")
		if s.Authenticator != nil && len(headers) == 1 {
			parts := strings.Fields(headers[0])
			if len(parts) == 2 && strings.EqualFold(parts[0], "Bearer") && len(parts[1]) <= 16384 {
				id, err = s.Authenticator.Authenticate(r.Context(), parts[1])
			}
		}
		if errors.Is(err, auth.ErrInsufficientScope) {
			s.audit("authorization.denied", id.UserID, "scope", "")
			w.Header().Set("WWW-Authenticate", `Bearer error="insufficient_scope", scope="cask:sessions"`)
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		if err != nil || id.UserID == "" || id.ExpiresAt.IsZero() || !time.Now().Before(id.ExpiresAt) {
			s.audit("authentication.failed", "", "authenticate", "")
			w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
			http.Error(w, "not authenticated", http.StatusUnauthorized)
			return
		}
		s.audit("authentication.succeeded", id.UserID, "authenticate", "")
		ctx, cancel := context.WithDeadline(auth.WithIdentity(r.Context(), id), id.ExpiresAt)
		defer cancel()
		next(w, r.WithContext(ctx))
	}
}

func (s *Server) authorize(r *http.Request, action, ownerID, sessionID string) bool {
	id := auth.FromContext(r.Context())
	allowed := id.UserID != "" && ownerID != "" && id.UserID == ownerID
	if s.Authorizer != nil {
		allowed = allowed && s.Authorizer.Allow(r.Context(), id, action, ownerID)
	}
	if id.UserID == "" || !time.Now().Before(id.ExpiresAt) {
		allowed = false
	}
	event := "authorization.denied"
	if allowed {
		event = "authorization.allowed"
	}
	s.audit(event, id.UserID, action, sessionID)
	return allowed
}

func (s *Server) audit(event, userID, action, sessionID string) {
	logger := s.Audit
	if logger == nil {
		logger = defaultAudit
	}
	logger.Info(event, "event", event, "user_id", userID, "action", action, "session_id", sessionID)
}
