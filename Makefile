KIND_CLUSTER ?= agentcask-mvp
SESSION_NAMESPACE ?= agentcask-sessions
GOARCH ?= $(shell go env GOARCH)

.PHONY: build linux-build test tidy helm-lint helm-template kind-up kind-build-images kind-load kind-deploy kind-test kind-down clean

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
	helm template agentcask charts/agentcask --include-crds >/tmp/agentcask-helm.yaml

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

kind-down:
	kind delete cluster --name "$(KIND_CLUSTER)"

clean:
	rm -rf bin
