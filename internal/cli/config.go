package cli

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

type Config struct {
	APIServer string
	Token     string
}

func LoadConfig(path string) Config {
	cfg := Config{APIServer: "http://127.0.0.1:8080", Token: "dev-token"}
	if path == "" {
		if home, err := os.UserHomeDir(); err == nil {
			path = filepath.Join(home, ".caskctl", "config.yaml")
		}
	}
	if path != "" {
		if file, err := os.Open(path); err == nil {
			defer file.Close()
			scanner := bufio.NewScanner(file)
			for scanner.Scan() {
				line := strings.TrimSpace(scanner.Text())
				if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, ":") {
					continue
				}
				parts := strings.SplitN(line, ":", 2)
				key := strings.TrimSpace(parts[0])
				value := strings.Trim(strings.TrimSpace(parts[1]), `"'`)
				switch key {
				case "apiServer":
					cfg.APIServer = value
				case "token":
					cfg.Token = value
				}
			}
		}
	}
	if v := os.Getenv("CASK_API_SERVER"); v != "" {
		cfg.APIServer = v
	}
	if v := os.Getenv("CASK_TOKEN"); v != "" {
		cfg.Token = v
	}
	return cfg
}
