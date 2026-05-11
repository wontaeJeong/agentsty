package redact

import "testing"

func TestRedactSensitiveValues(t *testing.T) {
	in := "Authorization: Bearer abc OPENAI_API_KEY=" + Sentinel
	out := String(in)
	if out == in || contains(out, Sentinel) || contains(out, "Bearer abc") {
		t.Fatalf("redaction failed: %q", out)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
