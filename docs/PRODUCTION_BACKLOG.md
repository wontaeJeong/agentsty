# Production Engineering Backlog

기준: origin/main `bc98d80` (2026-10-25). 요청 참조 `60745d4` 이후 정책 PR까지 머지된 상태에서 재검증했다. `make test` 통과는 unit/mock 기준선이며 opt-in kind/runtime 실행 증거가 아니다. **현재 Production 배포 불가.**

## P0: 반드시 해소할 출시 차단 항목

| ID | 실제 코드 근거 / 현재 결함 | 독립 구현 순서 및 완료 증거 |
| --- | --- | --- |
| P0-1 | `internal/api/server.go:userFromRequest`가 임의 Bearer를 dev-user, user: 접두사를 임의 소유자로 해석. `cmd/cask-api/main.go`에 인증 설정 없음 | 1a JWT/JWKS 검증·소유권·감사·설정 fail closed(이번 PR); 1b CLI device flow/안전한 저장/refresh; 1c 조직·프로젝트 권한 및 실제 IdP의 revoke/expiry/rotation 시나리오. 401/403·타인 CRUD/terminal 부정 테스트 + 실제 IdP E2E |
| P0-2 | `internal/modelproxy/token.go:secret`, controller DefaultConfig와 CLI flags, Helm values에 공개 개발 HMAC 기본값. resolver가 nil이면 토큰만으로 통과. 이름+만료 서명만 있고 UID/owner/purpose/key ID 없음 | 2a 기본 키 제거/기존 Secret 필수/시작 검증; 2b UID+owner+audience+purpose+jti·회전 key ring/철회; 삭제/동명 재생성/만료/키 회전/로그 누출 부정 테스트 |
| P0-3 | `internal/controller/controller.go:BuildPod`는 sleep 루프, repo spec을 checkout에 사용하지 않음. writable rootfs이며 workspace volume 없음 | 3a Git URL/host/주소 정책 및 commit 고정; 3b 승인된 Git credential broker·checkout 상태·PVC/보존; 3c patch/artifact 수집. 실제 저장소 clone→수정 E2E, SSRF/DNS rebinding/프로토콜/권한 실패 테스트 |
| P0-4 | `internal/modelproxy/proxy.go`: upstream 미설정이면 200 fake 성공. 무제한 ReadAll, 전체 header 전달, io.Copy에 SSE flush 보장 없음, modelRef routing 없음 | 4a upstream 필수·bounded stream/SSE·취소/timeout/동시성/request ID; 4b provider/model allowlist adapter·안전한 header/오류; 4c usage/rate/budget/failover. mock임을 명시한 provider 테스트 + 실제 provider/OpenCode 호환 검증 |
| P0-5 | `BuildPod`: non-root/cap drop/seccomp/resources는 이미 존재하므로 재구현 제외. automount token 기본, writable rootfs, Pod 소유 UID 미검증. `charts/.../values.yaml`의 kata handler는 runc | 5a PSA/automount false/volume/rootfs/UID; 5b 검증된 RuntimeClass 및 CNI egress 정책. 강한 실제 격리/CNI enforcement/metadata/K8s 차단은 대상 cluster에서 증거 필요; 이름만 kata는 미충족 |
| P0-6 | `terminal.DefaultCommand`: 도구 미설치 시 shell fallback. AllowedTools는 5개를 허용하나 runtime 지원 증거 없음. runtime test는 설치/터미널 중심 | 6a 실제 지원 도구만 allowlist+버전 고정 adapter; 6b checkout→모델→파일 수정→결과→중단/재접속. 1/2/3/4/5에 의존. 실제 agent E2E 필수 |

P0 병렬 가능 경계: 인증/CLI, 토큰/Secret, workspace, gateway, runtime isolation. 전체 통합 경로는 신뢰 가능한 identity·token·checkout·model·isolation이 모두 필요하다. UI는 이 경로보다 뒤다.

## P1: 운영 안정성 및 자동화

| ID | 기준 구현 / 다음 단위 | 종료 증거 |
| --- | --- | --- |
| P1-1 | controller `Run/reconcileAll`은 2초 전체 list, PodSucceeded도 Running으로 처리, status 매번 patch. informer+queue/conflict/leader election/conditions/finalizer/TTL | 다중 replica/restart/conflict/unschedulable/cleanup retry 실제 cluster 장애 주입 |
| P1-2 | API create/list/get/delete만 존재. start/stop/restart/idle/TTL extension/history/idempotency/concurrency policy 없음 | CRD orchestration과 영속 history 분리 ADR, lifecycle/cleanup/recovery/중복 생성 E2E |
| P1-3 | gateway가 모든 Origin 허용, frame/동시성/write deadline/heartbeat 없음. 종료 감시는 2초 polling | 소유권 재검증·expiry 종료부터 강화 후 bounded I/O, reconnect·slow consumer·goroutine/race/부하 검증 |
| P1-4 | userId owner 단위만 존재; org/project/quota/budget 없음 | 영속 identity/policy 모델, tenant 간 권한/자원 고갈/공정성 검증 |
| P1-5 | 구조화된 감사 이외 metrics/tracing/SLO 운영 증거 없음 | request/session correlation, OTel/Prometheus, dashboard/alert/runbook 실제 장애 진단 및 복구 실측 |
| P1-6 | Helm은 dev 이미지/resources 빈 값/replica 1, API의 issuer 설정도 없음 | dev/staging/prod 분리/필수 설정/Secret/PDB/topology/probes/digest, 설치/upgrade/rollback/HA. API group 변경은 GA 전 ADR/변환/마이그레이션을 통해서만 |
| P1-7 | `.github/workflows/ci.yml`에 formatting/tidy/test/build/runtime/render가 있었다. 이번에 race/vet/Go vulnerability gate 추가. 현재 환경 초기 scan에서 기존 Go1.26.3/x/net/x/text/spdystream 관련 도달 가능 22건을 발견하여 Go1.26.10/x/net0.60/x/text0.42/spdystream0.5.1 및 요구된 x/sys/x/term 버전으로 갱신. 재검사에서 No vulnerabilities found | 컨테이너·Kubernetes scan/SBOM/signing/provenance/release promotion/upgrade·rollback gate는 잔여. Go scan은 컨테이너/실행 격리를 증명하지 않음 |

## P2: 제품 기능

| ID | 구현 단위 / 의존성 | 종료 증거 |
| --- | --- | --- |
| P2-1 | CLI device login/refresh는 P0-1b로 당김. profiles/keyring/JSON/watch/wait/results/completion/version/지원 OS | fake OAuth unit + 실제 IdP login/refresh/logout, terminal raw mode/resize/재접속, OS CI |
| P2-2 | 관리 UI 허용. 별도 business logic 없이 동일 API에 로그인/세션/terminal/results/usage/admin/audit | P0 완료 후 한국어 UX/접근성/390px·1440px 실제 browser + 보안 E2E |
| P2-3 | 각 tool adapter/image/version/model 설정을 개별 출시 단위로 검증. 미지원 도구는 지원 표기 금지 | 도구별 실제 repository/model/file/result compatibility matrix |

## 이번 단위의 한계와 환경 의존성

- 1a만으로 P0-1 전체 완료라고 하지 않는다. OAuth device login/refresh 및 IdP 토큰 즉시 철회는 별도 단위다. JWT는 exp까지 유효하며 알려진 JWKS는 캐시된다.
- Production IdP/client 등록, 실제 Provider credential, 승인된 Git repository/credential, 강한 격리 runtime/CNI cluster, 목표 규모/SLO는 아직 제공/검증되지 않았다.
- 위 항목의 재현 절차와 실행 결과는 기능별 운영 가이드/검증 보고서에 추가한다. 가짜 값을 Production 설정으로 기본 제공하지 않는다.
