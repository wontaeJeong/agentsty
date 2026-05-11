package modelproxy

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const tokenPrefix = "cask-proxy"

const DefaultTokenTTL = 2 * time.Hour

type TokenManager struct {
	Secret string
	TTL    time.Duration
	Now    func() time.Time
}

func (m TokenManager) Generate(sessionID string) string {
	return m.GenerateUntil(sessionID, m.now().Add(m.ttl()))
}

func (m TokenManager) GenerateUntil(sessionID string, expiresAt time.Time) string {
	expiry := expiresAt.Unix()
	payload := fmt.Sprintf("%s.%d", sessionID, expiry)
	mac := hmac.New(sha256.New, []byte(m.secret()))
	_, _ = mac.Write([]byte(payload))
	sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return fmt.Sprintf("%s.%s.%d.%s", tokenPrefix, sessionID, expiry, sig)
}

func (m TokenManager) Validate(token string) (string, bool) {
	sessionID, _, ok := m.ValidateWithExpiry(token)
	return sessionID, ok
}

func (m TokenManager) ValidateWithExpiry(token string) (string, time.Time, bool) {
	parts := strings.Split(token, ".")
	if len(parts) != 4 || parts[0] != tokenPrefix {
		return "", time.Time{}, false
	}
	expiry, err := strconv.ParseInt(parts[2], 10, 64)
	if err != nil {
		return "", time.Time{}, false
	}
	expiresAt := time.Unix(expiry, 0).UTC()
	if !m.now().Before(expiresAt) {
		return "", expiresAt, false
	}
	payload := parts[1] + "." + parts[2]
	mac := hmac.New(sha256.New, []byte(m.secret()))
	_, _ = mac.Write([]byte(payload))
	expectedSig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	expected := tokenPrefix + "." + parts[1] + "." + parts[2] + "." + expectedSig
	if !hmac.Equal([]byte(expected), []byte(token)) {
		return "", expiresAt, false
	}
	return parts[1], expiresAt, true
}

func (m TokenManager) secret() string {
	if m.Secret == "" {
		return "dev-session-proxy-secret"
	}
	return m.Secret
}

func (m TokenManager) ttl() time.Duration {
	if m.TTL > 0 {
		return m.TTL
	}
	return DefaultTokenTTL
}

func (m TokenManager) now() time.Time {
	if m.Now != nil {
		return m.Now().UTC()
	}
	return time.Now().UTC()
}
