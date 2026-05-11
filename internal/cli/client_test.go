package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
)

func TestRunCreateSendsJSONAndPrintsID(t *testing.T) {
	var got CreateRequest
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/sessions" || r.Method != http.MethodPost {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer test-token" {
			t.Fatalf("missing authorization")
		}
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Fatal(err)
		}
		_, _ = w.Write([]byte(`{"id":"sess-test","phase":"Pending","tool":"stub","modelRef":"default","resourceProfile":"small","isolationProfile":"default"}`))
	}))
	defer server.Close()
	t.Setenv("CASK_API_SERVER", server.URL)
	t.Setenv("CASK_TOKEN", "test-token")
	out := new(bytes.Buffer)
	code := Run(context.Background(), []string{"session", "create", "--tool", "stub", "--repo", "https://example.invalid/repo.git"}, IOStreams{In: strings.NewReader(""), Out: out, Err: new(bytes.Buffer)})
	if code != 0 {
		t.Fatalf("run exited %d", code)
	}
	if got.Tool != "stub" || got.RepoURL == "" {
		t.Fatalf("bad create request: %+v", got)
	}
	if !strings.Contains(out.String(), "ID: sess-test") {
		t.Fatalf("unexpected output: %q", out.String())
	}
}

func TestRunGetAllowsOutputFlagAfterID(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/sessions/sess-test" || r.Method != http.MethodGet {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		_, _ = w.Write([]byte(`{"id":"sess-test","phase":"Running","tool":"stub","modelRef":"default","resourceProfile":"small","isolationProfile":"default"}`))
	}))
	defer server.Close()
	t.Setenv("CASK_API_SERVER", server.URL)
	t.Setenv("CASK_TOKEN", "test-token")
	out := new(bytes.Buffer)
	code := Run(context.Background(), []string{"session", "get", "sess-test", "-o", "json"}, IOStreams{In: strings.NewReader(""), Out: out, Err: new(bytes.Buffer)})
	if code != 0 {
		t.Fatalf("run exited %d", code)
	}
	if !strings.Contains(out.String(), `"id":"sess-test"`) {
		t.Fatalf("unexpected output: %q", out.String())
	}
}

func TestRunListPrintsAgeColumn(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/sessions" || r.Method != http.MethodGet {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		_, _ = w.Write([]byte(`{"items":[{"id":"sess-test","phase":"Running","tool":"stub","modelRef":"default","resourceProfile":"small","isolationProfile":"default","createdAt":"2026-05-11T00:00:00Z"}]}`))
	}))
	defer server.Close()
	t.Setenv("CASK_API_SERVER", server.URL)
	t.Setenv("CASK_TOKEN", "test-token")
	out := new(bytes.Buffer)
	code := Run(context.Background(), []string{"session", "list"}, IOStreams{In: strings.NewReader(""), Out: out, Err: new(bytes.Buffer)})
	if code != 0 {
		t.Fatalf("run exited %d", code)
	}
	if !strings.Contains(out.String(), "AGE") || !strings.Contains(out.String(), "sess-test") {
		t.Fatalf("unexpected list output: %q", out.String())
	}
}

func TestClientConnectForwardsBytes(t *testing.T) {
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatal(err)
		}
		defer conn.Close()
		_, payload, err := conn.ReadMessage()
		if err != nil {
			t.Fatal(err)
		}
		if string(payload) != "ping" {
			t.Fatalf("unexpected payload %q", payload)
		}
		_ = conn.WriteMessage(websocket.BinaryMessage, []byte("pong"))
	}))
	defer server.Close()
	client := Client{Config: Config{APIServer: server.URL, Token: "dev-token"}}
	out := new(bytes.Buffer)
	ctx := t.Context()
	if err := client.Connect(ctx, "sess-test", strings.NewReader("ping"), out); err != nil {
		t.Fatal(err)
	}
	if out.String() != "pong" {
		t.Fatalf("connect output %q", out.String())
	}
}
