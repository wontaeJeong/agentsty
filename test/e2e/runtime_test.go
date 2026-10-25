package e2e

import (
	"context"
	"os"
	"testing"
	"time"

	"agentcask/internal/controller"
)

func TestRuntimeSupportsRepositoryWorkAndPersistentTerminal(t *testing.T) {
	if os.Getenv("RUN_RUNTIME_TEST") != "1" {
		t.Skip("set RUN_RUNTIME_TEST=1 to test the built runtime image")
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	run(t, ctx, os.Environ(), "docker", "run", "--rm", "--user", "65532:65532",
		"-e", "HOME=/tmp/cask", "--entrypoint", "/bin/sh", controller.DefaultRuntimeImage, "-ec", `
mkdir -p "$HOME"
opencode --version
git --version
ssh -V
git init /tmp/repo
tmux new-session -d -s runtime-check 'sleep 30'
tmux has-session -t runtime-check
tmux kill-session -t runtime-check
`)
}
