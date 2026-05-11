package isolation

import (
	"context"
	"fmt"
	"maps"

	corev1 "k8s.io/api/core/v1"
	nodev1 "k8s.io/api/node/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type Profile struct {
	RuntimeClassName string
	NodeSelector     map[string]string
	Tolerations      []corev1.Toleration
}

type Profiles map[string]Profile

func DefaultProfiles() Profiles {
	return Profiles{
		"default": {RuntimeClassName: ""},
		"kata":    {RuntimeClassName: "kata"},
	}
}

func (p Profiles) Resolve(name string) (Profile, error) {
	profile, ok := p[name]
	if !ok || name == "" {
		return Profile{}, fmt.Errorf("unsupported isolation profile %q", name)
	}
	return profile, nil
}

func Apply(p Profile, pod *corev1.Pod) {
	if p.RuntimeClassName != "" {
		pod.Spec.RuntimeClassName = &p.RuntimeClassName
	}
	if len(p.NodeSelector) > 0 {
		pod.Spec.NodeSelector = map[string]string{}
		maps.Copy(pod.Spec.NodeSelector, p.NodeSelector)
	}
	if len(p.Tolerations) > 0 {
		pod.Spec.Tolerations = append([]corev1.Toleration{}, p.Tolerations...)
	}
}

func CheckRuntimeClass(ctx context.Context, kube kubernetes.Interface, p Profile) error {
	if p.RuntimeClassName == "" {
		return nil
	}
	_, err := kube.NodeV1().RuntimeClasses().Get(ctx, p.RuntimeClassName, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		return fmt.Errorf("runtimeclass %q not found", p.RuntimeClassName)
	}
	return err
}

func FakeRuntimeClass(name string) *nodev1.RuntimeClass {
	return &nodev1.RuntimeClass{ObjectMeta: metav1.ObjectMeta{Name: name}, Handler: "runc"}
}
