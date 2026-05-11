package redact

import (
	"net/http"
	"regexp"
	"strings"
)

const Sentinel = "REAL_UPSTREAM_KEY_SHOULD_NEVER_LEAK"

var sensitiveHeaderNames = map[string]struct{}{
	"authorization":     {},
	"cookie":            {},
	"set-cookie":        {},
	"x-api-key":         {},
	"openai-api-key":    {},
	"anthropic-api-key": {},
}

var valuePatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)(Authorization:\s*Bearer\s+)[^\s]+`),
	regexp.MustCompile(`(?i)((OPENAI_API_KEY|ANTHROPIC_API_KEY|CASK_SESSION_TOKEN)\s*=\s*)[^\s]+`),
}

func String(in string) string {
	out := strings.ReplaceAll(in, Sentinel, "[REDACTED]")
	for _, pattern := range valuePatterns {
		out = pattern.ReplaceAllString(out, `${1}[REDACTED]`)
	}
	return out
}

func Header(h http.Header) http.Header {
	out := http.Header{}
	for key, values := range h {
		if _, sensitive := sensitiveHeaderNames[strings.ToLower(key)]; sensitive {
			out.Set(key, "[REDACTED]")
			continue
		}
		for _, value := range values {
			out.Add(key, String(value))
		}
	}
	return out
}

func ContainsSecretLikeKey(key string) bool {
	lower := strings.ToLower(key)
	fragments := []string{"apikey", "api_key", "password", "passwd", "secret", "credential", "privatekey", "private_key", "token", "runtimeclassname"}
	for _, fragment := range fragments {
		if strings.Contains(lower, fragment) {
			return true
		}
	}
	return false
}
