package cli

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadConfigFileAndEnv(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.yaml")
	if err := os.WriteFile(path, []byte("apiServer: http://file.example\ntoken: file-token\n"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg := LoadConfig(path)
	if cfg.APIServer != "http://file.example" || cfg.Token != "file-token" {
		t.Fatalf("file config not loaded: %+v", cfg)
	}
	t.Setenv("CASK_API_SERVER", "http://env.example")
	t.Setenv("CASK_TOKEN", "env-token")
	cfg = LoadConfig(path)
	if cfg.APIServer != "http://env.example" || cfg.Token != "env-token" {
		t.Fatalf("env overrides not loaded: %+v", cfg)
	}
}

func TestNoDevelopmentTokenDefault(t *testing.T) {
	t.Setenv("CASK_TOKEN", "")
	cfg := LoadConfig(filepath.Join(t.TempDir(), "missing.yaml"))
	if cfg.Token != "" {
		t.Fatal("CLI silently supplies a development credential")
	}
}
