package e2e

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"testing"
	"time"
)

const sentinel = "REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK"

func TestKindCreateConnectDeleteFlow(t *testing.T) {
	if os.Getenv("RUN_KIND_E2E") != "1" {
		t.Skip("set RUN_KIND_E2E=1 to run kind E2E")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Minute)
	defer cancel()
	systemNamespace := envDefault("CASK_SYSTEM_NAMESPACE", "agentcask-system")
	sessionNamespace := envDefault("CASK_SESSION_NAMESPACE", "agentcask-sessions")
	apiPort := envDefault("CASK_API_PORT", "18080")
	modelProxyPort := envDefault("CASK_MODEL_PROXY_PORT", "18081")
	apiURL := "http://127.0.0.1:" + apiPort
	modelProxyURL := "http://127.0.0.1:" + modelProxyPort
	portForward := exec.CommandContext(ctx, "kubectl", "-n", systemNamespace, "port-forward", "svc/cask-api", apiPort+":8080")
	portForward.Stdout = io.Discard
	portForward.Stderr = io.Discard
	if err := portForward.Start(); err != nil {
		t.Fatalf("start port-forward: %v", err)
	}
	defer func() {
		_ = portForward.Process.Kill()
		_ = portForward.Wait()
	}()
	modelProxyForward := exec.CommandContext(ctx, "kubectl", "-n", systemNamespace, "port-forward", "svc/cask-model-proxy", modelProxyPort+":8080")
	modelProxyForward.Stdout = io.Discard
	modelProxyForward.Stderr = io.Discard
	if err := modelProxyForward.Start(); err != nil {
		t.Fatalf("start model proxy port-forward: %v", err)
	}
	defer func() {
		_ = modelProxyForward.Process.Kill()
		_ = modelProxyForward.Wait()
	}()
	waitHTTP(t, ctx, apiURL+"/healthz")
	waitHTTP(t, ctx, modelProxyURL+"/healthz")
	caskctl := os.Getenv("CASKCTL_BIN")
	if caskctl == "" {
		caskctl = "caskctl"
	}
	env := append(os.Environ(), "CASK_API_SERVER="+apiURL, "CASK_TOKEN=dev-token")
	createOut := run(t, ctx, env, caskctl, "session", "create", "--tool", "stub", "--repo", "https://example.invalid/repo.git", "--branch", "main", "--model", "default", "--resource", "small", "--isolation", "default", "--ttl", "30m")
	assertNoLeak(t, "create output", createOut)
	sessionID := parseSessionID(t, createOut)
	waitSessionRunning(t, ctx, apiURL, sessionID)
	agentPodYAML := run(t, ctx, env, "kubectl", "-n", sessionNamespace, "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "yaml")
	assertNoLeak(t, "agent pod yaml", agentPodYAML)
	expectedModelProxyHost := "cask-model-proxy." + systemNamespace + ".svc.cluster.local"
	if !strings.Contains(agentPodYAML, expectedModelProxyHost) {
		t.Fatalf("agent pod does not point at separated model proxy service: %s", agentPodYAML)
	}
	agentPodName := strings.TrimSpace(run(t, ctx, env, "kubectl", "-n", sessionNamespace, "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "jsonpath={.items[0].metadata.name}"))
	opencodeOut := run(t, ctx, env, "kubectl", "-n", sessionNamespace, "exec", agentPodName, "--", "/bin/sh", "-lc", "command -v opencode >/dev/null && opencode --version")
	if strings.TrimSpace(opencodeOut) == "" {
		t.Fatal("agent runtime image did not report an opencode version")
	}
	assertNoLeak(t, "opencode version output", opencodeOut)
	sessionYAML := run(t, ctx, env, "kubectl", "-n", sessionNamespace, "get", "agentsession", sessionID, "-o", "yaml")
	assertNoLeak(t, "AgentSession yaml", sessionYAML)
	proxyToken := run(t, ctx, env, "kubectl", "-n", sessionNamespace, "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "jsonpath={.items[0].spec.containers[0].env[?(@.name==\"CASK_SESSION_TOKEN\")].value}")
	proxyOut := postModelProxy(t, ctx, modelProxyURL, strings.TrimSpace(proxyToken))
	if !strings.Contains(proxyOut, sessionID) {
		t.Fatalf("model proxy response missing session ID: %s", proxyOut)
	}
	assertNoLeak(t, "model proxy response", proxyOut)
	if status := postStatus(t, ctx, apiURL+"/internal/model-proxy/v1/chat/completions", strings.TrimSpace(proxyToken)); status != http.StatusNotFound {
		t.Fatalf("cask-api still serves model proxy route, status %d", status)
	}
	connectOut := runWithInput(t, ctx, env, "echo CASK_E2E_OK; exit\n", caskctl, "session", "connect", sessionID)
	if !strings.Contains(connectOut, "CASK_E2E_OK") {
		t.Fatalf("terminal output missing expected marker: %q", connectOut)
	}
	assertNoLeak(t, "connect output", connectOut)
	deleteOut := run(t, ctx, env, caskctl, "session", "delete", sessionID)
	assertNoLeak(t, "delete output", deleteOut)
	waitPodDeleted(t, ctx, sessionNamespace, sessionID)
	apiLogs := run(t, ctx, env, "kubectl", "-n", systemNamespace, "logs", "deploy/cask-api")
	modelProxyLogs := run(t, ctx, env, "kubectl", "-n", systemNamespace, "logs", "deploy/cask-model-proxy")
	controllerLogs := run(t, ctx, env, "kubectl", "-n", systemNamespace, "logs", "deploy/cask-controller")
	assertNoLeak(t, "cask-api logs", apiLogs)
	assertNoLeak(t, "cask-model-proxy logs", modelProxyLogs)
	assertNoLeak(t, "cask-controller logs", controllerLogs)
}

func postModelProxy(t *testing.T, ctx context.Context, baseURL, token string) string {
	t.Helper()
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, baseURL+"/internal/model-proxy/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("model proxy status %d: %s", resp.StatusCode, body)
	}
	return string(body)
}

func postStatus(t *testing.T, ctx context.Context, url, token string) int {
	t.Helper()
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	return resp.StatusCode
}

func waitHTTP(t *testing.T, ctx context.Context, url string) {
	t.Helper()
	for {
		select {
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		default:
		}
		resp, err := http.Get(url)
		if err == nil && resp.StatusCode == http.StatusOK {
			resp.Body.Close()
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func waitSessionRunning(t *testing.T, ctx context.Context, apiURL, id string) {
	t.Helper()
	for {
		select {
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		default:
		}
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, apiURL+"/api/v1/sessions/"+id, nil)
		req.Header.Set("Authorization", "Bearer dev-token")
		resp, err := http.DefaultClient.Do(req)
		if err == nil && resp.StatusCode == http.StatusOK {
			var body struct {
				Phase         string `json:"phase"`
				TerminalReady bool   `json:"terminalReady"`
			}
			_ = json.NewDecoder(resp.Body).Decode(&body)
			resp.Body.Close()
			if body.Phase == "Running" && body.TerminalReady {
				return
			}
		} else if resp != nil {
			resp.Body.Close()
		}
		time.Sleep(1 * time.Second)
	}
}

func waitPodDeleted(t *testing.T, ctx context.Context, namespace, sessionID string) {
	t.Helper()
	for {
		select {
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		default:
		}
		cmd := exec.CommandContext(ctx, "kubectl", "-n", namespace, "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "--no-headers")
		out, _ := cmd.CombinedOutput()
		if strings.TrimSpace(string(out)) == "" || strings.Contains(string(out), "No resources found") {
			return
		}
		time.Sleep(1 * time.Second)
	}
}

func run(t *testing.T, ctx context.Context, env []string, name string, args ...string) string {
	t.Helper()
	return runWithInput(t, ctx, env, "", name, args...)
}

func runWithInput(t *testing.T, ctx context.Context, env []string, input, name string, args ...string) string {
	t.Helper()
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Env = env
	cmd.Stdin = strings.NewReader(input)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &out
	if err := cmd.Run(); err != nil {
		t.Fatalf("%s %s failed: %v\n%s", name, strings.Join(args, " "), err, out.String())
	}
	return out.String()
}

func parseSessionID(t *testing.T, out string) string {
	t.Helper()
	re := regexp.MustCompile(`ID:\s+(sess-[a-z0-9]+)`)
	match := re.FindStringSubmatch(out)
	if len(match) != 2 {
		t.Fatalf("could not parse session ID from %q", out)
	}
	return match[1]
}

func assertNoLeak(t *testing.T, name, value string) {
	t.Helper()
	if strings.Contains(value, sentinel) {
		t.Fatalf("%s leaked sentinel %s", name, sentinel)
	}
	if strings.Contains(strings.ToLower(value), "podname") && !strings.Contains(name, "yaml") {
		t.Fatalf("%s exposed podName: %s", name, value)
	}
	_ = fmt.Sprintf
}

func envDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
