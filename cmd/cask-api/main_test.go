package main

import (
	"context"
	"testing"
)

func TestStartupRejectsMissingAuthenticationConfig(t *testing.T) {
	for _, key := range []string{"CASK_OIDC_ISSUER", "CASK_OIDC_AUDIENCE", "CASK_OIDC_JWKS_URL"} {
		t.Setenv(key, "")
	}
	if _, err := newAuthenticatorFromEnv(context.Background()); err == nil {
		t.Fatal("missing production identity configuration accepted")
	}
	t.Setenv("CASK_OIDC_ISSUER", "https://issuer.invalid")
	t.Setenv("CASK_OIDC_AUDIENCE", "cask-api")
	if _, err := newAuthenticatorFromEnv(context.Background()); err == nil {
		t.Fatal("missing JWKS config accepted")
	}
	t.Setenv("CASK_OIDC_JWKS_URL", "https://issuer.invalid/keys")
	if _, err := newAuthenticatorFromEnv(context.Background()); err != nil {
		t.Fatal(err)
	}
}
