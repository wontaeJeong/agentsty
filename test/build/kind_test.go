package build_test

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestParallelKindTestDoesNotRunClusterJobsBeforeAuthPreflight(t *testing.T) {
	if _, err := exec.LookPath("make"); err != nil {
		t.Skip("make unavailable")
	}
	makefile, err := filepath.Abs(filepath.Join("..", "..", "Makefile"))
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	marker := filepath.Join(dir, "cluster-side-effect")
	// Replace external cluster/image operations with a visible side effect. Slow
	// preflight slightly so siblings would execute under -j4 if not ordered.
	fixture := fmt.Sprintf("include %s\nkind-auth-check: pause-auth-check\npause-auth-check:\n\t@sleep 0.1\nkind-up kind-load kind-deploy kind-build-images linux-build build:\n\t@touch %q\n", makefile, marker)
	if err := os.WriteFile(filepath.Join(dir, "Makefile"), []byte(fixture), 0600); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"CASK_OIDC_ISSUER", "CASK_OIDC_AUDIENCE", "CASK_OIDC_JWKS_URL", "CASK_E2E_TOKEN"} {
		t.Setenv(key, "")
	}
	cmd := exec.Command("make", "-j4", "kind-test")
	cmd.Dir = dir
	out, err := cmd.CombinedOutput()
	if err == nil {
		t.Fatalf("missing authentication did not fail: %s", out)
	}
	if !strings.Contains(string(out), "kind-test requires") {
		t.Fatalf("failed for reason other than authentication: %s", out)
	}
	if _, err := os.Stat(marker); err == nil {
		t.Fatalf("cluster/image work ran before failed authentication preflight: %s", out)
	} else if !os.IsNotExist(err) {
		t.Fatal(err)
	}
}
