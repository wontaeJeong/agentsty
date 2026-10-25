// Package auth verifies externally issued JWT access tokens. There is no
// development-token mode; only explicit authenticators can resolve an identity.
package auth

import (
	"context"
	"crypto/sha256"
	"encoding/base32"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
)

var (
	ErrUnauthenticated   = errors.New("invalid access token")
	ErrInsufficientScope = errors.New("insufficient scope")
)

const SessionScope = "cask:sessions"

type Identity struct {
	UserID    string
	Issuer    string
	Subject   string
	ExpiresAt time.Time
}

type Authenticator interface {
	Authenticate(context.Context, string) (Identity, error)
}

type Config struct {
	Issuer   string
	Audience string
	JWKSURL  string
	// HTTPClient optionally supplies an operator-trusted CA transport. Redirects
	// are always disabled and the timeout is bounded, including with this client.
	HTTPClient *http.Client
}

type OIDC struct {
	verifier *oidc.IDTokenVerifier
	issuer   string
}

func NewOIDC(ctx context.Context, cfg Config) (*OIDC, error) {
	if !secureURL(cfg.Issuer) || !secureURL(cfg.JWKSURL) || strings.TrimSpace(cfg.Audience) == "" || strings.ContainsAny(cfg.Audience, " \t\r\n") {
		return nil, errors.New("OIDC requires HTTPS issuer and JWKS URLs and a nonempty audience")
	}
	client := &http.Client{}
	if cfg.HTTPClient != nil {
		*client = *cfg.HTTPClient
	}
	if client.Timeout <= 0 || client.Timeout > 5*time.Second {
		client.Timeout = 5 * time.Second
	}
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return errors.New("JWKS redirects forbidden") }
	keySet := oidc.NewRemoteKeySet(oidc.ClientContext(ctx, client), cfg.JWKSURL)
	return &OIDC{issuer: cfg.Issuer, verifier: oidc.NewVerifier(cfg.Issuer, keySet, &oidc.Config{
		ClientID:             cfg.Audience,
		SupportedSigningAlgs: []string{oidc.RS256, oidc.ES256},
	})}, nil
}

func (v *OIDC) Authenticate(ctx context.Context, raw string) (Identity, error) {
	if v == nil || v.verifier == nil || raw == "" || len(raw) > 16384 {
		return Identity{}, ErrUnauthenticated
	}
	token, err := v.verifier.Verify(ctx, raw)
	if err != nil || token.Issuer != v.issuer {
		return Identity{}, ErrUnauthenticated
	}
	var claims struct {
		Scope     string      `json:"scope"`
		NotBefore json.Number `json:"nbf"`
	}
	if err := token.Claims(&claims); err != nil || strings.TrimSpace(token.Subject) == "" || token.Expiry.IsZero() || !time.Now().Before(token.Expiry) {
		return Identity{}, ErrUnauthenticated
	}
	if claims.NotBefore != "" {
		nbf, err := claims.NotBefore.Float64()
		if err != nil || float64(time.Now().Unix()) < nbf {
			return Identity{}, ErrUnauthenticated
		}
	}
	// Encode the pair unambiguously; subjects and issuers are case sensitive.
	pair, _ := json.Marshal([]string{token.Issuer, token.Subject})
	hash := sha256.Sum256(pair)
	id := Identity{UserID: "u-" + strings.ToLower(base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(hash[:])), Issuer: token.Issuer, Subject: token.Subject, ExpiresAt: token.Expiry}
	for _, scope := range strings.Fields(claims.Scope) {
		if scope == SessionScope {
			return id, nil
		}
	}
	return id, ErrInsufficientScope
}

func secureURL(raw string) bool {
	u, err := url.Parse(raw)
	return err == nil && u.Scheme == "https" && u.Hostname() != "" && u.User == nil && u.RawQuery == "" && u.Fragment == ""
}

type identityKey struct{}

func WithIdentity(ctx context.Context, id Identity) context.Context {
	return context.WithValue(ctx, identityKey{}, id)
}
func FromContext(ctx context.Context) Identity {
	id, _ := ctx.Value(identityKey{}).(Identity)
	return id
}
