package auth_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"agentcask/internal/auth"
	"agentcask/internal/testutil/oidctest"
	"k8s.io/apimachinery/pkg/util/validation"
)

func verifier(t *testing.T, p *oidctest.Provider) *auth.OIDC {
	t.Helper()
	v, err := auth.NewOIDC(context.Background(), auth.Config{Issuer: p.Server.URL, Audience: "cask-api", JWKSURL: p.Server.URL + "/keys", HTTPClient: p.Server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	return v
}

func TestJWTValidation(t *testing.T) {
	p := oidctest.New(t)
	v := verifier(t, p)
	valid := p.Token(t, "alice", nil)
	identity, err := v.Authenticate(context.Background(), valid)
	if err != nil || identity.UserID == "" || identity.Subject != "alice" || identity.Issuer != p.Server.URL {
		t.Fatalf("valid JWT failed: identity=%+v err=%v", identity, err)
	}
	if errs := validation.IsValidLabelValue(identity.UserID); len(errs) > 0 {
		t.Fatal(errs)
	}
	for name, claims := range map[string]map[string]any{
		"issuer": {"iss": "https://untrusted.invalid"}, "audience": {"aud": "different-api"},
		"expired": {"exp": time.Now().Add(-time.Minute).Unix()}, "missing-exp": {"exp": nil},
		"missing-sub": {"sub": nil}, "blank-sub": {"sub": " "},
		"not-yet-valid": {"nbf": time.Now().Add(time.Hour).Unix()},
		"missing-scope": {"scope": nil}, "wrong-scope": {"scope": "cask:sessions-admin"},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := v.Authenticate(context.Background(), p.Token(t, "alice", claims)); err == nil {
				t.Fatal("invalid JWT accepted")
			}
		})
	}
	for _, token := range []string{"dev-token", "user:alice", "random", valid + "x", "eyJhbGciOiJub25lIn0.e30."} {
		if _, err := v.Authenticate(context.Background(), token); err == nil {
			t.Fatal("unverified credential accepted")
		}
	}
	bob, err := v.Authenticate(context.Background(), p.Token(t, "bob", nil))
	if err != nil || bob.UserID == identity.UserID {
		t.Fatal("different subjects share owner")
	}
	again, err := v.Authenticate(context.Background(), p.Token(t, "alice", nil))
	if err != nil || again.UserID != identity.UserID {
		t.Fatal("owner not stable across tokens")
	}
	p2 := oidctest.New(t)
	other, err := verifier(t, p2).Authenticate(context.Background(), p2.Token(t, "alice", nil))
	if err != nil || other.UserID == identity.UserID {
		t.Fatal("issuer not bound to owner")
	}
}

func TestJWKSRotationAndConcurrentVerification(t *testing.T) {
	p := oidctest.New(t)
	v := verifier(t, p)
	if _, err := v.Authenticate(context.Background(), p.Token(t, "alice", nil)); err != nil {
		t.Fatal(err)
	}
	p.Rotate(t, "second")
	token := p.Token(t, "alice", nil)
	var wg sync.WaitGroup
	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := v.Authenticate(context.Background(), token); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
	p.Rotate(t, "unavailable")
	p.Down()
	if _, err := v.Authenticate(context.Background(), p.Token(t, "alice", nil)); err == nil {
		t.Fatal("unknown key accepted while JWKS unavailable")
	}
}

func TestOIDCConfigurationFailsClosed(t *testing.T) {
	for _, cfg := range []auth.Config{
		{}, {Issuer: "https://id.invalid", Audience: "cask-api"},
		{Issuer: "http://id.invalid", Audience: "cask-api", JWKSURL: "https://id.invalid/keys"},
		{Issuer: "https://id.invalid", Audience: "cask-api", JWKSURL: "http://id.invalid/keys"},
		{Issuer: "https://user:password@id.invalid", Audience: "cask-api", JWKSURL: "https://id.invalid/keys"},
		{Issuer: "https://id.invalid", Audience: "", JWKSURL: "https://id.invalid/keys"},
	} {
		if _, err := auth.NewOIDC(context.Background(), cfg); err == nil {
			t.Fatal("unsafe/missing OIDC config accepted")
		}
	}
}

func TestJWKSRedirectRejected(t *testing.T) {
	p := oidctest.New(t)
	// A trusted JWKS endpoint must not delegate token-key trust through redirects.
	redirect := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, p.Server.URL+"/keys", http.StatusFound)
	}))
	defer redirect.Close()
	v, err := auth.NewOIDC(context.Background(), auth.Config{Issuer: p.Server.URL, Audience: "cask-api", JWKSURL: redirect.URL, HTTPClient: redirect.Client()})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := v.Authenticate(context.Background(), p.Token(t, "alice", nil)); err == nil {
		t.Fatal("redirected JWKS trusted")
	}
}

func TestIssuerMustMatchExactlyEvenForProviderAliases(t *testing.T) {
	p := oidctest.New(t)
	v, err := auth.NewOIDC(context.Background(), auth.Config{Issuer: "https://accounts.google.com", Audience: "cask-api", JWKSURL: p.Server.URL + "/keys", HTTPClient: p.Server.Client()})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := v.Authenticate(context.Background(), p.Token(t, "alice", map[string]any{"iss": "accounts.google.com"})); err == nil {
		t.Fatal("provider alias bypassed configured exact issuer")
	}
}
