package terminal

import (
	"context"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"github.com/gorilla/websocket"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type resolverFunc func(context.Context, string) (*agentv1.AgentSession, error)

func (f resolverFunc) Get(ctx context.Context, id string) (*agentv1.AgentSession, error) {
	return f(ctx, id)
}

type fakeBackend struct{ stream *fakeStream }

func (b *fakeBackend) Start(context.Context, ExecRequest) (ExecStream, error) { return b.stream, nil }

type fakeStream struct {
	out     chan []byte
	mu      sync.Mutex
	writes  []byte
	resizes []Size
}

func newFakeStream() *fakeStream { return &fakeStream{out: make(chan []byte, 8)} }
func (s *fakeStream) Write(p []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.writes = append(s.writes, p...)
	return len(p), nil
}
func (s *fakeStream) Output() <-chan []byte { return s.out }
func (s *fakeStream) Resize(size Size) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.resizes = append(s.resizes, size)
	return nil
}
func (s *fakeStream) Close() error { return nil }

func TestGatewayBridgesBinaryAndResize(t *testing.T) {
	stream := newFakeStream()
	session := agentv1.NewAgentSession("sess-test", "agentcask-sessions", agentv1.AgentSessionSpec{UserID: "dev-user", Tool: "stub", Repo: agentv1.RepoSpec{URL: "https://example.invalid/repo.git", Branch: "main"}, ModelRef: "default", ResourceProfile: "small", Isolation: agentv1.IsolationSpec{Profile: "default"}, TTLSeconds: 7200}, metav1.Now())
	session.Status.Phase = agentv1.PhaseRunning
	session.Status.PodName = "agent-session-sess-test"
	session.Status.ContainerName = agentv1.ContainerName
	session.Status.TerminalReady = true
	gateway := &Gateway{Resolver: resolverFunc(func(context.Context, string) (*agentv1.AgentSession, error) { return session, nil }), Backend: &fakeBackend{stream: stream}, Timeout: time.Second}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { gateway.Serve(w, r, "dev-user", "sess-test") }))
	defer server.Close()
	url := "ws" + server.URL[len("http"):]
	conn, _, err := websocket.DefaultDialer.Dial(url, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	stream.out <- []byte("hello")
	messageType, payload, err := conn.ReadMessage()
	if err != nil {
		t.Fatal(err)
	}
	if messageType != websocket.BinaryMessage || string(payload) != "hello" {
		t.Fatalf("unexpected output: %d %q", messageType, payload)
	}
	if err := conn.WriteMessage(websocket.BinaryMessage, []byte("abc")); err != nil {
		t.Fatal(err)
	}
	if err := conn.WriteMessage(websocket.TextMessage, []byte(`{"type":"resize","cols":120,"rows":40}`)); err != nil {
		t.Fatal(err)
	}
	time.Sleep(50 * time.Millisecond)
	stream.mu.Lock()
	defer stream.mu.Unlock()
	if string(stream.writes) != "abc" {
		t.Fatalf("binary input not forwarded: %q", stream.writes)
	}
	if len(stream.resizes) != 1 || stream.resizes[0].Cols != 120 || stream.resizes[0].Rows != 40 {
		t.Fatalf("resize not forwarded: %#v", stream.resizes)
	}
}

func TestDefaultCommandPrefersOpenCodeWithTmux(t *testing.T) {
	cmd := strings.Join(DefaultCommand("opencode"), " ")
	if !strings.Contains(cmd, "tmux new-session") || !strings.Contains(cmd, "opencode") {
		t.Fatalf("opencode command does not use tmux/opencode: %v", DefaultCommand("opencode"))
	}
	stub := strings.Join(DefaultCommand("stub"), " ")
	if strings.Contains(stub, "tmux") || !strings.Contains(stub, "cask-stub-tui") {
		t.Fatalf("stub command should stay deterministic without tmux: %v", DefaultCommand("stub"))
	}
}

type backendFunc func(context.Context, ExecRequest) (ExecStream, error)

func (f backendFunc) Start(ctx context.Context, req ExecRequest) (ExecStream, error) {
	return f(ctx, req)
}

type closingStream struct {
	*fakeStream
	closed chan struct{}
	once   sync.Once
}

func (s *closingStream) Close() error {
	s.once.Do(func() { close(s.closed); close(s.out) })
	return nil
}

func TestConnectedTerminalRechecksOwnerAndResolverErrors(t *testing.T) {
	for _, failure := range []string{"owner-changed", "resolver-failed"} {
		t.Run(failure, func(t *testing.T) {
			var invalid atomic.Bool
			session := agentv1.NewAgentSession("sess-watch", "agentcask-sessions", agentv1.AgentSessionSpec{UserID: "alice", Tool: "stub", TTLSeconds: 7200}, metav1.Now())
			session.Status.Phase = agentv1.PhaseRunning
			session.Status.TerminalReady = true
			session.Status.PodName = "agent-session-sess-watch"
			stream := &closingStream{fakeStream: newFakeStream(), closed: make(chan struct{})}
			backendCtx := make(chan context.Context, 1)
			gateway := &Gateway{Resolver: resolverFunc(func(context.Context, string) (*agentv1.AgentSession, error) {
				copy := *session
				if invalid.Load() {
					if failure == "owner-changed" {
						copy.Spec.UserID = "bob"
					} else {
						return &copy, errors.New("resolver unavailable")
					}
				}
				return &copy, nil
			}), Backend: backendFunc(func(ctx context.Context, _ ExecRequest) (ExecStream, error) { backendCtx <- ctx; return stream, nil })}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { gateway.Serve(w, r, "alice", "sess-watch") }))
			defer server.Close()
			conn, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(server.URL, "http"), nil)
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			ctx := <-backendCtx
			invalid.Store(true)
			_ = conn.SetReadDeadline(time.Now().Add(4 * time.Second))
			_, _, err = conn.ReadMessage()
			if err == nil {
				t.Fatal("invalid owner/resolver left connection open")
			}
			if nerr, ok := err.(net.Error); ok && nerr.Timeout() {
				t.Fatal("authorization polling did not close connection")
			}
			select {
			case <-stream.closed:
			case <-time.After(time.Second):
				t.Fatal("backend not closed")
			}
			select {
			case <-ctx.Done():
			case <-time.After(time.Second):
				t.Fatal("backend context not cancelled")
			}
		})
	}
}
