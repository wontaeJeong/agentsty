# Production Engineering — 첫 구현 단위 검증 기록

## 판정과 범위

**Production 배포 불가.** P0-1a API 인증/소유권 경계와 발견된 Go 의존성 취약점을 수정했다. P0-1 전체, 실제 IdP·cluster 인증 통합 및 P0-2~6/P1/P2 전체가 완료된 것은 아니다. [백로그](../PRODUCTION_BACKLOG.md)에서 잔여 항목을 추적한다.

기준 origin/main `bc98d80` (요청 참조 `60745d4` 이후). 전용 `feat/production-auth-boundary` 브랜치/워크트리를 사용했고 기본 checkout에서 제품 파일을 수정하거나 직접 배포하지 않았다.

## 구현 및 커밋

| 커밋 | 주요 변경 |
| --- | --- |
| `9d8e795` | 실제 코드 근거의 P0/P1/P2 백로그 및 첫 구현 계획 |
| `b29dba7` | `internal/auth` JWT/JWKS 검증, `internal/api` 인증/소유권/감사, `cmd/cask-api` 필수 설정, terminal Origin/만료 종료, CLI 개발 토큰 기본값 제거, Helm/kind/E2E 계약 및 ADR/운영 문서 |
| `bb5a1a5` | Go1.26.10 및 x/net/x/text/spdystream 보안 수정과 종속 업데이트, CI race/vet/취약점 gate |

## 해결한 결함과 회귀 근거

- 초기 회귀 테스트에서 임의 문자열·dev-token·user:alice가 모두 200으로 인증되는 것을 재현했다. 이후 미설정 서버에서도 401이며 runtime fallback은 없다.
- TLS JWKS fixture로 검증된 서명/정확한 issuer/audience/exp/sub/nbf 및 `cask:sessions` scope를 검사했다. 변조/unsigned/잘못된 issuer·audience·누락 exp·빈 sub·미래 nbf·scope prefix 혼동을 거부한다.
- 라이브러리의 Google issuer 별칭 허용도 테스트에서 재현한 뒤 명시적인 exact-match 검사로 차단했다.
- 같은 issuer/sub는 토큰 갱신 후 같은 label-safe owner를, 다른 issuer/sub는 다른 owner를 갖는다. 타인 GET/DELETE/terminal은 403, 목록은 owner만 보인다.
- JWT 만료 시 터미널 종료, 외부 Origin 거부, 인증/권한 감사 이벤트와 JWT 비노출을 확인했다.
- 필수 인증 env 누락 시 시작 검증이 실패한다. Helm의 누락 설정 렌더는 실패하고 명시적 설정은 API env로 전달된다. render-only fixture를 실제 IdP로 표시하지 않았다.
- 최초 govulncheck는 Go1.26.3 및 기존 x/net/x/text/spdystream에서 도달 가능한 취약점 22건을 보고했다. 수정 후 고정된 govulncheck v1.9.0은 `No vulnerabilities found`를 보고했다. OS·container·runtime 격리 scan까지 통과한 의미는 아니다.

## 실행 결과

환경: macOS arm64, Go `go1.26.10`, Helm `v4.2.0`, Docker Engine `29.2.1`. Linux amd64는 cross-compile 결과이며 Linux 실제 실행/배포 증거가 아니다.

| 명령 | 결과 / 한계 |
| --- | --- |
| `make test` | PASS. opt-in kind/runtime 테스트는 기본 실행에서 SKIP |
| `go test -race ./...` | PASS. 실제 cluster/IdP가 아닌 unit/mock/fixture 경로 |
| `go vet ./...` | PASS |
| `make build` | PASS |
| `CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build ./cmd/...` | PASS (cross-compile) |
| `make security-test` | PASS, `No vulnerabilities found` (govulncheck v1.9.0) |
| `make helm-lint` | PASS. chart icon 권고 1개, 실패 0 |
| `make helm-template` | PASS, render-only OIDC fixture 사용 |
| `go test ./test/helm -count=1` | PASS, 필수 설정 누락 4종 거부 및 양성 렌더 |
| `go test ./test/build -count=1` | PASS, 외부 작업을 marker로 대체한 parallel make preflight barrier 검증 |
| `kubectl kustomize --load-restrictor=LoadRestrictionsNone deploy/kind` | PASS (렌더만; 설치 아님) |
| `make runtime-test` | PASS. 기존 이미지의 tool 설치/파일 작업/지속 터미널 기준선, 모델 호출/agent 파일 수정 E2E 아님 |
| `make kind-test` | **BLOCKED/실패**: 테스트 IdP issuer/audience/JWKS 및 `CASK_E2E_TOKEN` 미제공으로 preflight exit 2. 기존 kind cluster 변경 없음 |
| `git diff --check` | PASS |

## 독립 리뷰와 수정 검증

독립 읽기 전용 리뷰에서 Critical은 없었으나 생성 정책 우회와 회귀 테스트 공백이 Important로 발견되었다. 다음 수정은 각각 실패를 확인한 뒤 전체 테스트/race/vet/native·Linux-amd64 build/Go scan/Helm/runtime 검증을 재실행했고 모두 PASS했다(실제 IdP/kind 차단은 변함없음). 수정 코드는 후속 리뷰 대응 커밋으로 별도 기록한다.

- 추가 정책이 모든 작업을 거부해도 create가 201/실제 persistence 1회를 수행하는 것을 재현했다. 이제 body 처리/persistence 전에 정책을 확인하여 403/생성 0회/denied audit를 보장한다.
- `nbf=현재+1분` JWT를 추가하여 go-oidc의 5분 leeway보다 엄격한 검사를 검증한다. 사용자 정의 검사를 제거하면 새 테스트가 실패하고 복구하면 통과한다.
- 연결 후 owner 변경 및 resolver가 객체와 오류를 함께 반환하는 두 시나리오에서 WebSocket 종료/backend Close/context cancel을 확인한다. 해당 검사를 제거하면 두 테스트가 timeout으로 실패하고 복구하면 통과한다.
- 병렬 make의 preflight-before-side-effect 문제는 클러스터 변경 위험 때문에 Important로 재분류했다. 실제 외부 작업을 파일 marker로 대체한 `make -j4` 테스트에서 preflight 실패 전에 marker가 생성됨을 재현했고, prerequisite barrier+순차 submake로 수정한 후 marker가 생성되지 않음을 확인했다. 실제 cluster는 사용하지 않았다.
- ID token 제외 문구가 구현보다 강한 점도 배포 경계 오해 위험 때문에 Important로 재분류했다. type discriminator를 새로 강제하는 대신 실제 계약을 수정했다. API 전용 audience/scope를 ID token과 분리하는 것은 운영자 필수 검증 조건이며, 동일 claim의 신뢰된 JWT는 type만으로 거부되지 않는다.

리뷰가 판단하지 않은 실제 IdP/TLS/cluster, CLI/철회, 나머지 P0/terminal 전체 hardening은 미검증·미완료로 유지한다. reviewer가 재실행하지 않은 full build/vulnerability 검증은 작성자가 직접 수행한 결과만 기록한다. 이 구분을 생략하거나 리뷰만으로 Production 승인하지 않는다.

## 미완료, 잔존 위험 및 재현 절차

- 실제 IdP와 CLI device login/refresh/안전한 저장, 즉시 JWT 철회, org/project RBAC는 미완료다. 캐시된 JWKS의 기존 유효 JWT는 exp까지 사용 가능하다. JWT 만료/회전/비상 차단 절차와 기존 dev owner drain/migration은 [Runbook](../RUNBOOK.md#8-jwt-인증-운영-p0-1a)을 따른다.
- 실제 IdP에서 API audience, `cask:sessions` scope, RS256/ES256 JWT access token을 구성하고 issuer/JWKS HTTPS 연결을 확인한 뒤 별도 테스트 KUBECONFIG에서 `make kind-test`를 실행해야 한다. 첫 검증은 stub 기준선이므로 실제 checkout→model→file edit 통합 검증을 대체하지 않는다.
- 기존 공개 개발 HMAC 기본값, 부족한 model-token 범위/철회, Git checkout 부재, 모델 gateway fake 성공/스트리밍/사용량 정책, 강한 runtime/CNI 격리, controller/terminal/운영/배포 품질 결함은 [백로그](../PRODUCTION_BACKLOG.md)에 남아 있다.
- 감사 로그는 JSON stderr 출력까지만 구현했다. 수집·보존·권한·경보·보안 이벤트 연계는 배포별 검증이 필요하다. JWKS unknown-key abuse/rate-limit, terminal backpressure/heartbeat/UID는 후속 보안·운영 단위다.
- CI workflow는 수정했으나 원격 Actions 결과/이미지 scan/SBOM/signing/provenance/release promotion은 이 로컬 실행으로 검증되지 않았다.

main 직접 변경/운영 배포/자동 머지를 수행하지 않는다. 이 기록은 부분 개선의 증거이며 Production 출시 승인이 아니다.

## 실행 중 판단과 비용

- 전체 임무는 여러 독립 릴리스 단위이므로 가장 높은 위험의 P0-1a부터 구현했다. 비용: 이 PR이 전체 P0/P1/P2 완료를 의미하지 않으며 후속 구현이 필요하다.
- 네이티브 도구가 로컬 main에서 만든 detached worktree를 ff-only로 갱신하고 명시적으로 origin/main에서 작업 브랜치를 생성했다. 기본 checkout은 수정하지 않았다.
- 기존 git hook이 저장소에 없는 `.pre-commit-config.yaml`을 요구해 커밋이 차단되었다. hook 자체는 수정하지 않고 hook이 안내하는 `PRE_COMMIT_ALLOW_NO_CONFIG=1`을 사용했다. 비용: 존재하지 않는 pre-commit 설정의 추가 검사는 받을 수 없고 명시적 test/vet/race/scan 검증에 의존한다.
- 기존 도달 가능한 취약점 때문에 Go 최소 버전을 1.26.10으로 올렸다. 비용: 이전 Go toolchain 지원을 중단하며 자동 toolchain 다운로드 또는 운영 빌드 환경 갱신이 필요하다.
