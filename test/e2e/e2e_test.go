package e2e

import (
	"bufio"
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
	if os.Getenv("CASK_E2E_TOKEN") == "" {
		t.Fatal("CASK_E2E_TOKEN must contain a signed JWT for the configured test issuer; dev-token is not accepted")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Minute)
	defer cancel()
	apiURL := startPortForward(t, ctx, "cask-api")
	modelProxyURL := startPortForward(t, ctx, "cask-model-proxy")
	waitHTTP(t, ctx, apiURL+"/healthz")
	waitHTTP(t, ctx, modelProxyURL+"/healthz")
	caskctl := os.Getenv("CASKCTL_BIN")
	if caskctl == "" {
		caskctl = "caskctl"
	}
	env := append(os.Environ(), "CASK_API_SERVER="+apiURL, "CASK_TOKEN="+os.Getenv("CASK_E2E_TOKEN"))
	createOut := run(t, ctx, env, caskctl, "session", "create", "--tool", "stub", "--repo", "https://example.invalid/repo.git", "--branch", "main", "--model", "default", "--resource", "small", "--isolation", "default", "--ttl", "30m")
	assertNoLeak(t, "create output", createOut)
	sessionID := parseSessionID(t, createOut)
	waitSessionRunning(t, ctx, apiURL, sessionID)
	agentPodYAML := run(t, ctx, env, "kubectl", "-n", "agentcask-sessions", "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "yaml")
	assertNoLeak(t, "agent pod yaml", agentPodYAML)
	if !strings.Contains(agentPodYAML, "cask-model-proxy.agentcask-system.svc.cluster.local") {
		t.Fatalf("agent pod does not point at separated model proxy service: %s", agentPodYAML)
	}
	if !strings.Contains(agentPodYAML, "image: agentcask/agent-runtime:dev") {
		t.Fatalf("agent pod is not using the derived OpenCode runtime image: %s", agentPodYAML)
	}
	agentPodName := strings.TrimSpace(run(t, ctx, env, "kubectl", "-n", "agentcask-sessions", "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "jsonpath={.items[0].metadata.name}"))
	opencodeOut := run(t, ctx, env, "kubectl", "-n", "agentcask-sessions", "exec", agentPodName, "--", "/bin/sh", "-ec", "opencode --version; git --version; ssh -V; tmux -V")
	if strings.TrimSpace(opencodeOut) == "" {
		t.Fatal("agent runtime image did not report an opencode version")
	}
	assertNoLeak(t, "opencode version output", opencodeOut)
	sessionYAML := run(t, ctx, env, "kubectl", "-n", "agentcask-sessions", "get", "agentsession", sessionID, "-o", "yaml")
	assertNoLeak(t, "AgentSession yaml", sessionYAML)
	proxyToken := run(t, ctx, env, "kubectl", "-n", "agentcask-sessions", "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "-o", "jsonpath={.items[0].spec.containers[0].env[?(@.name==\"CASK_SESSION_TOKEN\")].value}")
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
	waitPodDeleted(t, ctx, sessionID)
	apiLogs := run(t, ctx, env, "kubectl", "-n", "agentcask-system", "logs", "deploy/cask-api")
	modelProxyLogs := run(t, ctx, env, "kubectl", "-n", "agentcask-system", "logs", "deploy/cask-model-proxy")
	controllerLogs := run(t, ctx, env, "kubectl", "-n", "agentcask-system", "logs", "deploy/cask-controller")
	assertNoLeak(t, "cask-api logs", apiLogs)
	assertNoLeak(t, "cask-model-proxy logs", modelProxyLogs)
	assertNoLeak(t, "cask-controller logs", controllerLogs)
}

func startPortForward(t *testing.T, ctx context.Context, service string) string {
	t.Helper()
	cmd := exec.CommandContext(ctx, "kubectl", "-n", "agentcask-system", "port-forward", "--address=127.0.0.1", "svc/"+service, ":8080")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		t.Fatalf("start %s port-forward: %v", service, err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	})
	ready := make(chan string, 1)
	go func() {
		defer close(ready)
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			var port int
			if _, err := fmt.Sscanf(scanner.Text(), "Forwarding from 127.0.0.1:%d -> 8080", &port); err == nil {
				ready <- fmt.Sprintf("http://127.0.0.1:%d", port)
			}
		}
	}()
	select {
	case url := <-ready:
		if url == "" {
			t.Fatalf("%s port-forward exited before becoming ready", service)
		}
		return url
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	case <-time.After(20 * time.Second):
		t.Fatalf("timed out starting %s port-forward", service)
	}
	return ""
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
		req.Header.Set("Authorization", "Bearer "+os.Getenv("CASK_E2E_TOKEN"))
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

func waitPodDeleted(t *testing.T, ctx context.Context, sessionID string) {
	t.Helper()
	for {
		select {
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		default:
		}
		cmd := exec.CommandContext(ctx, "kubectl", "-n", "agentcask-sessions", "get", "pod", "-l", "agentcask.aidev.samsungds.net/session-id="+sessionID, "--no-headers")
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
