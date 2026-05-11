package isolation

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
)

func TestApplyDefaultOmitsRuntimeClass(t *testing.T) {
	pod := &corev1.Pod{}
	profile, err := DefaultProfiles().Resolve("default")
	if err != nil {
		t.Fatal(err)
	}
	Apply(profile, pod)
	if pod.Spec.RuntimeClassName != nil {
		t.Fatalf("default profile set runtimeClassName: %q", *pod.Spec.RuntimeClassName)
	}
}

func TestApplyKataRuntimeClass(t *testing.T) {
	pod := &corev1.Pod{}
	profiles := Profiles{"kata": {RuntimeClassName: "kata", NodeSelector: map[string]string{"agentcask.aidev.samsungds.net/kata": "true"}}}
	profile, err := profiles.Resolve("kata")
	if err != nil {
		t.Fatal(err)
	}
	Apply(profile, pod)
	if pod.Spec.RuntimeClassName == nil || *pod.Spec.RuntimeClassName != "kata" {
		t.Fatalf("kata runtimeClassName not applied: %#v", pod.Spec.RuntimeClassName)
	}
	if pod.Spec.NodeSelector["agentcask.aidev.samsungds.net/kata"] != "true" {
		t.Fatal("kata nodeSelector not applied")
	}
}

func TestUnsupportedProfileFails(t *testing.T) {
	if _, err := DefaultProfiles().Resolve("raw-runtime"); err == nil {
		t.Fatal("unsupported profile accepted")
	}
}
