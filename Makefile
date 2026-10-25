KIND_CLUSTER ?= agentcask-mvp
SESSION_NAMESPACE ?= agentcask-sessions
GOARCH ?= $(shell go env GOARCH)
HELM_VALUES ?= charts/agentcask/ci/oidc-values.yaml

.PHONY: build linux-build test security-test runtime-test tidy helm-lint helm-template kind-up kind-build-images kind-load kind-deploy kind-auth-check kind-test kind-down clean

build:
	go build -o bin/cask-api ./cmd/cask-api
	go build -o bin/cask-controller ./cmd/cask-controller
	go build -o bin/cask-model-proxy ./cmd/cask-model-proxy
	go build -o bin/caskctl ./cmd/caskctl

test:
	go test ./...

security-test:
	go run golang.org/x/vuln/cmd/govulncheck@v1.9.0 ./...

runtime-test:
	RUN_RUNTIME_TEST=1 go test ./test/e2e/... -run TestRuntimeSupportsRepositoryWorkAndPersistentTerminal -count=1

tidy:
	go mod tidy

helm-lint:
	helm lint charts/agentcask -f $(HELM_VALUES)

helm-template:
	helm template agentcask charts/agentcask -f $(HELM_VALUES) --include-crds

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
	@test -n "$$CASK_OIDC_ISSUER" -a -n "$$CASK_OIDC_AUDIENCE" -a -n "$$CASK_OIDC_JWKS_URL" || { echo "Set CASK_OIDC_ISSUER, CASK_OIDC_AUDIENCE and CASK_OIDC_JWKS_URL (HTTPS test IdP required)" >&2; exit 1; }
	kubectl apply -f config/crd
	kubectl apply -f deploy/kind/namespace.yaml
	kubectl -n agentcask-system create configmap cask-api-auth --from-literal=CASK_OIDC_ISSUER="$$CASK_OIDC_ISSUER" --from-literal=CASK_OIDC_AUDIENCE="$$CASK_OIDC_AUDIENCE" --from-literal=CASK_OIDC_JWKS_URL="$$CASK_OIDC_JWKS_URL" --dry-run=client -o yaml | kubectl apply -f -
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

kind-auth-check:
	@test -n "$$CASK_OIDC_ISSUER" -a -n "$$CASK_OIDC_AUDIENCE" -a -n "$$CASK_OIDC_JWKS_URL" -a -n "$$CASK_E2E_TOKEN" || { echo "kind-test requires CASK_OIDC_ISSUER/AUDIENCE/JWKS_URL and CASK_E2E_TOKEN; no dev authentication fallback" >&2; exit 1; }

kind-test: kind-auth-check kind-up kind-load kind-deploy
	RUN_KIND_E2E=1 CASKCTL_BIN=$(CURDIR)/bin/caskctl go test ./test/e2e/... -count=1 -timeout=5m

kind-down:
	kind delete cluster --name "$(KIND_CLUSTER)"

clean:
	rm -rf bin
