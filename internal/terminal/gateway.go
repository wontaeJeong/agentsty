package terminal

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	agentv1 "agentcask/api/v1alpha1"
	"github.com/gorilla/websocket"
)

type SessionResolver interface {
	Get(ctx context.Context, id string) (*agentv1.AgentSession, error)
}

type ExecRequest struct {
	Namespace     string
	PodName       string
	ContainerName string
	Command       []string
}

type Size struct {
	Cols uint16
	Rows uint16
}

type ExecStream interface {
	Write([]byte) (int, error)
	Output() <-chan []byte
	Resize(Size) error
	Close() error
}

type ExecBackend interface {
	Start(ctx context.Context, req ExecRequest) (ExecStream, error)
}

type Gateway struct {
	Resolver SessionResolver
	Backend  ExecBackend
	Upgrader websocket.Upgrader
	Timeout  time.Duration
}

func (g *Gateway) Serve(w http.ResponseWriter, r *http.Request, userID, sessionID string) {
	if g.Resolver == nil || g.Backend == nil {
		http.Error(w, "terminal gateway not configured", http.StatusServiceUnavailable)
		return
	}
	session, err := g.Resolver.Get(r.Context(), sessionID)
	if err != nil {
		http.Error(w, "session not found", http.StatusNotFound)
		return
	}
	if session.Spec.UserID != userID {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	if session.Status.Phase != agentv1.PhaseRunning || !session.Status.TerminalReady || session.Status.PodName == "" {
		http.Error(w, "session not ready", http.StatusConflict)
		return
	}
	upgrader := g.Upgrader
	if upgrader.CheckOrigin == nil {
		upgrader.CheckOrigin = func(*http.Request) bool { return true }
	}
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()
	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()
	stream, err := g.Backend.Start(ctx, ExecRequest{
		Namespace:     session.Namespace,
		PodName:       session.Status.PodName,
		ContainerName: defaultString(session.Status.ContainerName, agentv1.ContainerName),
		Command:       DefaultCommand(session.Spec.Tool),
	})
	if err != nil {
		_ = conn.WriteMessage(websocket.TextMessage, []byte(`{"type":"error","message":"exec failed"}`))
		return
	}
	defer stream.Close()
	go g.closeWhenSessionStops(ctx, cancel, conn, stream, sessionID)

	done := make(chan struct{})
	var writeMu sync.Mutex
	go func() {
		defer close(done)
		defer conn.Close()
		for out := range stream.Output() {
			writeMu.Lock()
			err := conn.WriteMessage(websocket.BinaryMessage, out)
			writeMu.Unlock()
			if err != nil {
				return
			}
		}
	}()

	if timeout := g.timeout(); timeout > 0 {
		_ = conn.SetReadDeadline(time.Now().Add(timeout))
	}
	for {
		select {
		case <-done:
			return
		default:
		}
		messageType, payload, err := conn.ReadMessage()
		if err != nil {
			return
		}
		if timeout := g.timeout(); timeout > 0 {
			_ = conn.SetReadDeadline(time.Now().Add(timeout))
		}
		switch messageType {
		case websocket.BinaryMessage:
			if _, err := stream.Write(payload); err != nil {
				return
			}
		case websocket.TextMessage:
			_ = handleControl(payload, stream)
		case websocket.CloseMessage:
			return
		}
	}
}

func DefaultCommand(tool string) []string {
	toolCommand := map[string]string{
		"stub":        "if [ -x /usr/local/bin/cask-stub-tui ]; then /usr/local/bin/cask-stub-tui; else /bin/sh; fi",
		"opencode":    "if command -v opencode >/dev/null 2>&1; then opencode; else /bin/sh; fi",
		"claude-code": "if command -v claude >/dev/null 2>&1; then claude; else /bin/sh; fi",
		"codex":       "if command -v codex >/dev/null 2>&1; then codex; else /bin/sh; fi",
		"openclaw":    "if command -v openclaw >/dev/null 2>&1; then openclaw; else /bin/sh; fi",
		"hermes":      "if command -v hermes >/dev/null 2>&1; then hermes; else /bin/sh; fi",
	}
	cmd := toolCommand[tool]
	if cmd == "" {
		cmd = "/bin/sh"
	}
	if tool == "stub" {
		return []string{"/bin/sh", "-lc", cmd}
	}
	return []string{"/bin/sh", "-lc", "if command -v tmux >/dev/null 2>&1; then tmux new-session -A -s agent '" + shellQuote(cmd) + "'; else " + cmd + "; fi"}
}

func (g *Gateway) closeWhenSessionStops(ctx context.Context, cancel context.CancelFunc, conn *websocket.Conn, stream ExecStream, sessionID string) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			session, err := g.Resolver.Get(ctx, sessionID)
			if err != nil || session == nil || session.DeletionTimestamp != nil || session.Status.Phase == agentv1.PhaseExpired || session.Status.Phase == agentv1.PhaseTerminating || session.Status.Phase == agentv1.PhaseFailed || !session.Status.TerminalReady {
				_ = stream.Close()
				_ = conn.Close()
				cancel()
				return
			}
		}
	}
}

func shellQuote(s string) string {
	return strings.ReplaceAll(s, "'", "'\\''")
}

func handleControl(payload []byte, stream ExecStream) error {
	var msg struct {
		Type string `json:"type"`
		Cols uint16 `json:"cols"`
		Rows uint16 `json:"rows"`
	}
	if err := json.Unmarshal(payload, &msg); err != nil {
		return err
	}
	if msg.Type == "resize" && msg.Cols > 0 && msg.Rows > 0 {
		return stream.Resize(Size{Cols: msg.Cols, Rows: msg.Rows})
	}
	return nil
}

func (g *Gateway) timeout() time.Duration {
	if g.Timeout == 0 {
		return 30 * time.Minute
	}
	return g.Timeout
}

func defaultString(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}

type EchoBackend struct{}

func (EchoBackend) Start(ctx context.Context, _ ExecRequest) (ExecStream, error) {
	stream := &echoStream{out: make(chan []byte, 16), closed: make(chan struct{})}
	stream.out <- []byte("cask terminal ready\n")
	go func() {
		<-ctx.Done()
		_ = stream.Close()
	}()
	return stream, nil
}

type echoStream struct {
	out    chan []byte
	closed chan struct{}
	once   sync.Once
}

func (s *echoStream) Write(p []byte) (int, error) {
	select {
	case <-s.closed:
		return 0, io.ErrClosedPipe
	case s.out <- append([]byte{}, p...):
		return len(p), nil
	}
}

func (s *echoStream) Output() <-chan []byte { return s.out }
func (s *echoStream) Resize(Size) error     { return nil }

func (s *echoStream) Close() error {
	s.once.Do(func() {
		close(s.closed)
		close(s.out)
	})
	return nil
}

var ErrExecNotConfigured = errors.New("exec backend not configured")
