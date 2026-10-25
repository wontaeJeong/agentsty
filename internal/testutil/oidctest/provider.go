// Package oidctest provides a local signed-JWT/JWKS fixture, not a real IdP.
// It must never be wired into a runtime binary or deployment.
package oidctest

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

type Provider struct {
	Server *httptest.Server
	mu     sync.Mutex
	key    *rsa.PrivateKey
	kid    string
	down   bool
}

func New(t testing.TB) *Provider {
	t.Helper()
	p := &Provider{}
	p.Rotate(t, "first")
	p.Server = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p.mu.Lock()
		defer p.mu.Unlock()
		if p.down {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		if r.URL.Path != "/keys" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"keys": []any{map[string]any{
			"kty": "RSA", "kid": p.kid, "alg": "RS256", "use": "sig",
			"n": base64.RawURLEncoding.EncodeToString(p.key.N.Bytes()),
			"e": base64.RawURLEncoding.EncodeToString(big.NewInt(int64(p.key.E)).Bytes()),
		}}})
	}))
	t.Cleanup(p.Server.Close)
	return p
}

func (p *Provider) Rotate(t testing.TB, kid string) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.key, p.kid = key, kid
}

func (p *Provider) Down() { p.mu.Lock(); defer p.mu.Unlock(); p.down = true }

func (p *Provider) Token(t testing.TB, subject string, overrides map[string]any) string {
	t.Helper()
	claims := map[string]any{"iss": p.Server.URL, "sub": subject, "aud": "cask-api", "exp": time.Now().Add(time.Hour).Unix(), "iat": time.Now().Unix(), "scope": "cask:sessions"}
	for k, v := range overrides {
		if v == nil {
			delete(claims, k)
		} else {
			claims[k] = v
		}
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	header, _ := json.Marshal(map[string]string{"alg": "RS256", "kid": p.kid, "typ": "at+jwt"})
	body, err := json.Marshal(claims)
	if err != nil {
		t.Fatal(err)
	}
	message := base64.RawURLEncoding.EncodeToString(header) + "." + base64.RawURLEncoding.EncodeToString(body)
	hash := sha256.Sum256([]byte(message))
	sig, err := rsa.SignPKCS1v15(rand.Reader, p.key, crypto.SHA256, hash[:])
	if err != nil {
		t.Fatal(err)
	}
	return message + "." + base64.RawURLEncoding.EncodeToString(sig)
}
