package helm_test

import (
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestChartRequiresExplicitOIDCConfiguration(t *testing.T) {
	if _, err := exec.LookPath("helm"); err != nil {
		t.Skip("helm is required for chart rendering tests")
	}
	chart := filepath.Join("..", "..", "charts", "agentcask")
	for _, tc := range []struct {
		name  string
		args  []string
		valid bool
	}{
		{"unset", nil, false},
		{"missing-audience", []string{"--set", "api.oidc.issuer=https://issuer.invalid", "--set", "api.oidc.jwksURL=https://issuer.invalid/keys"}, false},
		{"missing-issuer", []string{"--set", "api.oidc.audience=cask-api", "--set", "api.oidc.jwksURL=https://issuer.invalid/keys"}, false},
		{"missing-jwks", []string{"--set", "api.oidc.issuer=https://issuer.invalid", "--set", "api.oidc.audience=cask-api"}, false},
		{"explicit", []string{"--set", "api.oidc.issuer=https://issuer.invalid", "--set", "api.oidc.audience=cask-api", "--set", "api.oidc.jwksURL=https://issuer.invalid/keys"}, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			args := append([]string{"template", "test", chart}, tc.args...)
			out, err := exec.Command("helm", args...).CombinedOutput()
			if tc.valid {
				if err != nil {
					t.Fatalf("explicit configuration failed: %v %s", err, out)
				}
				for _, env := range []string{"CASK_OIDC_ISSUER", "CASK_OIDC_AUDIENCE", "CASK_OIDC_JWKS_URL"} {
					if !strings.Contains(string(out), env) {
						t.Errorf("missing runtime setting %s", env)
					}
				}
			} else if err == nil {
				t.Fatal("missing authentication configuration rendered successfully")
			}
		})
	}
}
