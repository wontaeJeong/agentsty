package api

import (
	"context"
	"fmt"
	"maps"
	"sync"

	agentv1 "agentcask/api/v1alpha1"
)

type MemoryStore struct {
	mu       sync.Mutex
	sessions map[string]*agentv1.AgentSession
	AutoRun  bool
}

func NewMemoryStore(autoRun bool) *MemoryStore {
	return &MemoryStore{sessions: map[string]*agentv1.AgentSession{}, AutoRun: autoRun}
}

func (m *MemoryStore) Ready(context.Context) error { return nil }

func (m *MemoryStore) Create(_ context.Context, session *agentv1.AgentSession) (*agentv1.AgentSession, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	copySession := *session
	if m.AutoRun {
		copySession.Status.Phase = agentv1.PhaseRunning
		copySession.Status.PodName = "memory-" + session.Name
		copySession.Status.ContainerName = agentv1.ContainerName
		copySession.Status.TerminalReady = true
	}
	m.sessions[session.Name] = &copySession
	return clone(&copySession), nil
}

func (m *MemoryStore) List(_ context.Context, userID string) ([]agentv1.AgentSession, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var out []agentv1.AgentSession
	for _, session := range m.sessions {
		if userID == "" || session.Spec.UserID == userID {
			out = append(out, *clone(session))
		}
	}
	return out, nil
}

func (m *MemoryStore) Get(_ context.Context, id string) (*agentv1.AgentSession, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	session, ok := m.sessions[id]
	if !ok {
		return nil, fmt.Errorf("session %s not found", id)
	}
	return clone(session), nil
}

func (m *MemoryStore) Delete(_ context.Context, id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.sessions[id]; !ok {
		return fmt.Errorf("session %s not found", id)
	}
	delete(m.sessions, id)
	return nil
}

func clone(in *agentv1.AgentSession) *agentv1.AgentSession {
	out := *in
	out.Labels = map[string]string{}
	maps.Copy(out.Labels, in.Labels)
	return &out
}
