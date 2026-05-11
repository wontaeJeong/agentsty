package terminal

import (
	"context"
	"io"
	"net/url"
	"sync"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

type KubernetesExecBackend struct {
	Client kubernetes.Interface
	Config *rest.Config
}

func (b KubernetesExecBackend) Start(ctx context.Context, req ExecRequest) (ExecStream, error) {
	if b.Client == nil || b.Config == nil {
		return nil, ErrExecNotConfigured
	}
	stdinReader, stdinWriter := io.Pipe()
	out := make(chan []byte, 32)
	resizeQueue := newResizeQueue()
	stream := &kubeExecStream{stdin: stdinWriter, out: out, resize: resizeQueue, done: make(chan struct{})}

	reqURL := b.Client.CoreV1().RESTClient().Post().
		Resource("pods").
		Namespace(req.Namespace).
		Name(req.PodName).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Container: req.ContainerName,
			Command:   req.Command,
			Stdin:     true,
			Stdout:    true,
			Stderr:    true,
			TTY:       true,
		}, scheme.ParameterCodec).
		URL()
	exec, err := remotecommand.NewSPDYExecutor(b.Config, "POST", reqURL)
	if err != nil {
		_ = stdinReader.Close()
		_ = stdinWriter.Close()
		return nil, err
	}
	go func() {
		defer close(out)
		defer close(stream.done)
		writer := outputWriter{out: out}
		_ = exec.StreamWithContext(ctx, remotecommand.StreamOptions{
			Stdin:             stdinReader,
			Stdout:            writer,
			Stderr:            writer,
			Tty:               true,
			TerminalSizeQueue: resizeQueue,
		})
	}()
	return stream, nil
}

type kubeExecStream struct {
	stdin  *io.PipeWriter
	out    <-chan []byte
	resize *resizeQueue
	done   chan struct{}
	once   sync.Once
}

func (s *kubeExecStream) Write(p []byte) (int, error) { return s.stdin.Write(p) }
func (s *kubeExecStream) Output() <-chan []byte       { return s.out }
func (s *kubeExecStream) Resize(size Size) error {
	s.resize.Push(size)
	return nil
}
func (s *kubeExecStream) Close() error {
	s.once.Do(func() {
		_ = s.stdin.Close()
	})
	return nil
}

type outputWriter struct{ out chan<- []byte }

func (w outputWriter) Write(p []byte) (int, error) {
	copyBytes := append([]byte{}, p...)
	w.out <- copyBytes
	return len(p), nil
}

type resizeQueue struct {
	ch chan remotecommand.TerminalSize
}

func newResizeQueue() *resizeQueue { return &resizeQueue{ch: make(chan remotecommand.TerminalSize, 8)} }

func (q *resizeQueue) Push(size Size) {
	select {
	case q.ch <- remotecommand.TerminalSize{Width: size.Cols, Height: size.Rows}:
	default:
	}
}

func (q *resizeQueue) Next() *remotecommand.TerminalSize {
	size, ok := <-q.ch
	if !ok {
		return nil
	}
	return &size
}

var _ = metav1.NamespaceDefault
var _ = schema.GroupVersion{}
var _ = url.URL{}
