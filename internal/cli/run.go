package cli

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"golang.org/x/term"
)

type IOStreams struct {
	In  io.Reader
	Out io.Writer
	Err io.Writer
}

func Run(ctx context.Context, args []string, streams IOStreams) int {
	if streams.In == nil {
		streams.In = os.Stdin
	}
	if streams.Out == nil {
		streams.Out = os.Stdout
	}
	if streams.Err == nil {
		streams.Err = os.Stderr
	}
	if len(args) == 0 || args[0] == "--help" || args[0] == "-h" {
		usage(streams.Out)
		return 0
	}
	if args[0] != "session" || len(args) < 2 {
		fmt.Fprintln(streams.Err, "expected session command")
		usage(streams.Err)
		return 2
	}
	cfg := LoadConfig("")
	client := Client{Config: cfg}
	switch args[1] {
	case "create":
		return runCreate(ctx, client, args[2:], streams)
	case "list":
		return runList(ctx, client, args[2:], streams)
	case "get":
		return runGet(ctx, client, args[2:], streams)
	case "delete":
		return runDelete(ctx, client, args[2:], streams)
	case "connect":
		return runConnect(ctx, client, args[2:], streams)
	default:
		fmt.Fprintf(streams.Err, "unknown session command %q\n", args[1])
		return 2
	}
}

func runCreate(ctx context.Context, client Client, args []string, streams IOStreams) int {
	fs := flag.NewFlagSet("session create", flag.ContinueOnError)
	fs.SetOutput(streams.Err)
	tool := fs.String("tool", "stub", "agent tool")
	repo := fs.String("repo", "", "repository URL")
	branch := fs.String("branch", "main", "repository branch")
	model := fs.String("model", "default", "model reference")
	resource := fs.String("resource", "small", "resource profile")
	isolationProfile := fs.String("isolation", "default", "isolation profile")
	ttl := fs.Duration("ttl", 2*time.Hour, "session ttl")
	output := fs.String("o", "", "output format")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	session, raw, err := client.Create(ctx, CreateRequest{Tool: *tool, RepoURL: *repo, Branch: *branch, ModelRef: *model, ResourceProfile: *resource, IsolationProfile: *isolationProfile, TTLSeconds: int64(ttl.Seconds())})
	if err != nil {
		fmt.Fprintln(streams.Err, err)
		return 1
	}
	if *output == "json" {
		_, _ = streams.Out.Write(raw)
		return 0
	}
	fmt.Fprintf(streams.Out, "ID: %s\nPhase: %s\n", session.ID, session.Phase)
	return 0
}

func runList(ctx context.Context, client Client, args []string, streams IOStreams) int {
	fs := flag.NewFlagSet("session list", flag.ContinueOnError)
	fs.SetOutput(streams.Err)
	output := fs.String("o", "", "output format")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	items, raw, err := client.List(ctx)
	if err != nil {
		fmt.Fprintln(streams.Err, err)
		return 1
	}
	if *output == "json" {
		_, _ = streams.Out.Write(raw)
		return 0
	}
	fmt.Fprintln(streams.Out, "ID\tTOOL\tPHASE\tISOLATION\tAGE")
	for _, item := range items {
		fmt.Fprintf(streams.Out, "%s\t%s\t%s\t%s\t%s\n", item.ID, item.Tool, item.Phase, item.IsolationProfile, age(item.CreatedAt))
	}
	return 0
}

func runGet(ctx context.Context, client Client, args []string, streams IOStreams) int {
	output, positional, err := parseGetArgs(args)
	if err != nil {
		fmt.Fprintln(streams.Err, err)
		return 2
	}
	if len(positional) != 1 {
		fmt.Fprintln(streams.Err, "session id required")
		return 2
	}
	session, raw, err := client.Get(ctx, positional[0])
	if err != nil {
		fmt.Fprintln(streams.Err, err)
		return 1
	}
	if output == "json" {
		_, _ = streams.Out.Write(raw)
		return 0
	}
	fmt.Fprintf(streams.Out, "ID: %s\nPhase: %s\nTool: %s\nIsolation: %s\nTerminalReady: %t\n", session.ID, session.Phase, session.Tool, session.IsolationProfile, session.TerminalReady)
	return 0
}

func age(createdAt string) string {
	if createdAt == "" {
		return "-"
	}
	created, err := time.Parse(time.RFC3339, createdAt)
	if err != nil {
		return "-"
	}
	d := time.Since(created).Round(time.Second)
	if d < time.Minute {
		return fmt.Sprintf("%ds", int(d.Seconds()))
	}
	if d < time.Hour {
		return fmt.Sprintf("%dm", int(d.Minutes()))
	}
	return fmt.Sprintf("%dh", int(d.Hours()))
}

func parseGetArgs(args []string) (string, []string, error) {
	var output string
	positional := make([]string, 0, 1)
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch {
		case arg == "-o":
			if i+1 >= len(args) {
				return "", nil, fmt.Errorf("-o requires a value")
			}
			output = args[i+1]
			i++
		case strings.HasPrefix(arg, "-o="):
			output = strings.TrimPrefix(arg, "-o=")
		default:
			positional = append(positional, arg)
		}
	}
	return output, positional, nil
}

func runDelete(ctx context.Context, client Client, args []string, streams IOStreams) int {
	fs := flag.NewFlagSet("session delete", flag.ContinueOnError)
	fs.SetOutput(streams.Err)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() != 1 {
		fmt.Fprintln(streams.Err, "session id required")
		return 2
	}
	if _, err := client.Delete(ctx, fs.Arg(0)); err != nil {
		fmt.Fprintln(streams.Err, err)
		return 1
	}
	fmt.Fprintf(streams.Out, "deleted: %s\n", fs.Arg(0))
	return 0
}

func runConnect(ctx context.Context, client Client, args []string, streams IOStreams) int {
	fs := flag.NewFlagSet("session connect", flag.ContinueOnError)
	fs.SetOutput(streams.Err)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() != 1 {
		fmt.Fprintln(streams.Err, "session id required")
		return 2
	}
	stdin, ok := streams.In.(*os.File)
	var oldState *term.State
	if ok && term.IsTerminal(int(stdin.Fd())) {
		state, err := term.MakeRaw(int(stdin.Fd()))
		if err == nil {
			oldState = state
			defer term.Restore(int(stdin.Fd()), oldState)
		}
	}
	if err := client.Connect(ctx, fs.Arg(0), streams.In, streams.Out); err != nil {
		if !strings.Contains(err.Error(), "normal") {
			fmt.Fprintln(streams.Err, err)
			return 1
		}
	}
	return 0
}

func usage(w io.Writer) {
	enc := json.NewEncoder(io.Discard)
	_ = enc
	fmt.Fprintln(w, "Usage: caskctl session <create|list|get|connect|delete>")
}
