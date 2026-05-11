package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

type Client struct {
	Config Config
	HTTP   *http.Client
}

type CreateRequest struct {
	Tool             string `json:"tool"`
	RepoURL          string `json:"repoUrl"`
	Branch           string `json:"branch"`
	ModelRef         string `json:"modelRef"`
	ResourceProfile  string `json:"resourceProfile"`
	IsolationProfile string `json:"isolationProfile"`
	TTLSeconds       int64  `json:"ttlSeconds"`
}

type Session struct {
	ID               string `json:"id"`
	Phase            string `json:"phase"`
	Reason           string `json:"reason,omitempty"`
	Message          string `json:"message,omitempty"`
	Tool             string `json:"tool"`
	ModelRef         string `json:"modelRef"`
	ResourceProfile  string `json:"resourceProfile"`
	IsolationProfile string `json:"isolationProfile"`
	TerminalReady    bool   `json:"terminalReady,omitempty"`
	CreatedAt        string `json:"createdAt,omitempty"`
	ExpiresAt        string `json:"expiresAt,omitempty"`
	TerminalURL      string `json:"terminalUrl,omitempty"`
}

func (c Client) Create(ctx context.Context, req CreateRequest) (Session, []byte, error) {
	return c.doSession(ctx, http.MethodPost, "/api/v1/sessions", req)
}

func (c Client) List(ctx context.Context) ([]Session, []byte, error) {
	var parsed struct {
		Items []Session `json:"items"`
	}
	body, err := c.do(ctx, http.MethodGet, "/api/v1/sessions", nil)
	if err != nil {
		return nil, body, err
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, body, err
	}
	return parsed.Items, body, nil
}

func (c Client) Get(ctx context.Context, id string) (Session, []byte, error) {
	return c.doSession(ctx, http.MethodGet, "/api/v1/sessions/"+url.PathEscape(id), nil)
}

func (c Client) Delete(ctx context.Context, id string) ([]byte, error) {
	return c.do(ctx, http.MethodDelete, "/api/v1/sessions/"+url.PathEscape(id), nil)
}

func (c Client) Connect(ctx context.Context, id string, in io.Reader, out io.Writer) error {
	base, err := url.Parse(strings.TrimRight(c.Config.APIServer, "/"))
	if err != nil {
		return err
	}
	if base.Scheme == "https" {
		base.Scheme = "wss"
	} else {
		base.Scheme = "ws"
	}
	base.Path = "/api/v1/sessions/" + url.PathEscape(id) + "/terminal"
	header := http.Header{"Authorization": []string{"Bearer " + c.Config.Token}}
	conn, _, err := websocket.DefaultDialer.DialContext(ctx, base.String(), header)
	if err != nil {
		return err
	}
	defer conn.Close()
	errCh := make(chan error, 2)
	go func() {
		buf := make([]byte, 4096)
		for {
			n, readErr := in.Read(buf)
			if n > 0 {
				if writeErr := conn.WriteMessage(websocket.BinaryMessage, append([]byte{}, buf[:n]...)); writeErr != nil {
					errCh <- writeErr
					return
				}
			}
			if readErr != nil {
				return
			}
		}
	}()
	go func() {
		for {
			messageType, payload, readErr := conn.ReadMessage()
			if readErr != nil {
				errCh <- nil
				return
			}
			if messageType == websocket.BinaryMessage || messageType == websocket.TextMessage {
				if _, err := out.Write(payload); err != nil {
					errCh <- err
					return
				}
			}
		}
	}()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case err := <-errCh:
		return err
	}
}

func (c Client) doSession(ctx context.Context, method, path string, payload any) (Session, []byte, error) {
	body, err := c.do(ctx, method, path, payload)
	if err != nil {
		return Session{}, body, err
	}
	var session Session
	if err := json.Unmarshal(body, &session); err != nil {
		return Session{}, body, err
	}
	return session, body, nil
}

func (c Client) do(ctx context.Context, method, path string, payload any) ([]byte, error) {
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(c.Config.APIServer, "/")+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.Config.Token)
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	client := c.HTTP
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 300 {
		return data, fmt.Errorf("api error: %s", strings.TrimSpace(string(data)))
	}
	return data, nil
}
