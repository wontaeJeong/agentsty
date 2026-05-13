KIND_CLUSTER ?= agentcask-mvp
SESSION_NAMESPACE ?= agentcask-sessions
KIND_HELM_RELEASE ?= agentcask-helm
KIND_HELM_SYSTEM_NAMESPACE ?= agentcask-helm-system
KIND_HELM_SESSION_NAMESPACE ?= agentcask-helm-sessions
KIND_HELM_API_PORT ?= 18082
KIND_HELM_MODEL_PROXY_PORT ?= 18083
GOARCH ?= $(shell go env GOARCH)

.PHONY: build linux-build test tidy helm-lint helm-template kind-up kind-build-images kind-load kind-deploy kind-test kind-helm-clean kind-helm-deploy kind-helm-test kind-down clean

build:
	go build -o bin/cask-api ./cmd/cask-api
	go build -o bin/cask-controller ./cmd/cask-controller
	go build -o bin/cask-model-proxy ./cmd/cask-model-proxy
	go build -o bin/caskctl ./cmd/caskctl

test:
	go test ./...

tidy:
	go mod tidy

helm-lint:
	helm lint charts/agentcask

helm-template:
	helm template agentcask charts/agentcask --namespace agentcask-system --include-crds >/tmp/agentcask-helm.yaml

linux-build:
	mkdir -p bin/linux
	CGO_ENABLED=0 GOOS=linux GOARCH=$(GOARCH) go build -o bin/linux/cask-api ./cmd/cask-api
	CGO_ENABLED=0 GOOS=linux GOARCH=$(GOARCH) go build -o bin/linux/cask-controller ./cmd/cask-controller
	CGO_ENABLED=0 GOOS=linux GOARCH=$(GOARCH) go build -o bin/linux/cask-model-proxy ./cmd/cask-model-proxy

kind-up:
	@if kind get clusters | grep -qx "$(KIND_CLUSTER)"; then echo "kind cluster $(KIND_CLUSTER) already exists"; else kind create cluster --name "$(KIND_CLUSTER)"; fi

kind-build-images: linux-build build
	docker build -t agentcask/cask-api:dev -f build/cask-api.Dockerfile .
	docker build -t agentcask/cask-controller:dev -f build/cask-controller.Dockerfile .
	docker build -t agentcask/cask-model-proxy:dev -f build/cask-model-proxy.Dockerfile .
	docker build -t agentcask/agent-runtime:dev -f build/agent-runtime.Dockerfile .

kind-load: kind-build-images
	kind load docker-image --name "$(KIND_CLUSTER)" agentcask/cask-api:dev
	kind load docker-image --name "$(KIND_CLUSTER)" agentcask/cask-controller:dev
	kind load docker-image --name "$(KIND_CLUSTER)" agentcask/cask-model-proxy:dev
	kind load docker-image --name "$(KIND_CLUSTER)" agentcask/agent-runtime:dev

kind-deploy:
	kubectl apply -f config/crd
	kubectl apply -f deploy/kind/namespace.yaml
	kubectl apply -f deploy/kind/network-policy.yaml
	kubectl apply -f config/rbac/rbac.yaml
	kubectl apply -f deploy/kind/runtimeclass-kata.yaml
	kubectl apply -f deploy/kind/cask-api.yaml
	kubectl apply -f deploy/kind/cask-model-proxy.yaml
	kubectl apply -f deploy/kind/cask-controller.yaml
	kubectl -n agentcask-system rollout restart deploy/cask-api deploy/cask-controller deploy/cask-model-proxy
	kubectl -n agentcask-system rollout status deploy/cask-api --timeout=180s
	kubectl -n agentcask-system rollout status deploy/cask-model-proxy --timeout=180s
	kubectl -n agentcask-system rollout status deploy/cask-controller --timeout=180s

kind-test: kind-up kind-load kind-deploy
	RUN_KIND_E2E=1 CASKCTL_BIN=$(CURDIR)/bin/caskctl go test ./test/e2e/... -count=1 -timeout=5m

kind-helm-clean:
	-helm uninstall $(KIND_HELM_RELEASE) --namespace $(KIND_HELM_SYSTEM_NAMESPACE)
	-kubectl -n $(KIND_HELM_SESSION_NAMESPACE) get agentsessions -o name | while read resource; do kubectl -n $(KIND_HELM_SESSION_NAMESPACE) patch $$resource --type=merge -p '{"metadata":{"finalizers":[]}}'; done
	kubectl delete namespace $(KIND_HELM_SYSTEM_NAMESPACE) $(KIND_HELM_SESSION_NAMESPACE) --ignore-not-found=true --wait=true

kind-helm-deploy:
	helm upgrade --install $(KIND_HELM_RELEASE) charts/agentcask --namespace $(KIND_HELM_SYSTEM_NAMESPACE) --create-namespace --set namespaces.sessions.name=$(KIND_HELM_SESSION_NAMESPACE)
	kubectl -n $(KIND_HELM_SYSTEM_NAMESPACE) rollout status deploy/cask-api --timeout=180s
	kubectl -n $(KIND_HELM_SYSTEM_NAMESPACE) rollout status deploy/cask-model-proxy --timeout=180s
	kubectl -n $(KIND_HELM_SYSTEM_NAMESPACE) rollout status deploy/cask-controller --timeout=180s

kind-helm-test: kind-up kind-load kind-helm-clean kind-helm-deploy
	RUN_KIND_E2E=1 CASKCTL_BIN=$(CURDIR)/bin/caskctl CASK_SYSTEM_NAMESPACE=$(KIND_HELM_SYSTEM_NAMESPACE) CASK_SESSION_NAMESPACE=$(KIND_HELM_SESSION_NAMESPACE) CASK_API_PORT=$(KIND_HELM_API_PORT) CASK_MODEL_PROXY_PORT=$(KIND_HELM_MODEL_PROXY_PORT) go test ./test/e2e/... -count=1 -timeout=5m

kind-down:
	kind delete cluster --name "$(KIND_CLUSTER)"

clean:
	rm -rf bin
