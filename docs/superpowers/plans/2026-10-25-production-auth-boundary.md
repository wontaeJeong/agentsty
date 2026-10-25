# Production Authentication Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** P0-1의 임의 Bearer 신원 위조를 제거하고 검증된 JWT 기반 세션 소유권 경계를 구현한다. 전체 Production 작업의 첫 독립 단위다.

**Architecture:** Go API에 OIDC JWT authenticator를 주입한다. 신뢰된 설정의 HTTPS JWKS만 사용하고 서명/issuer/audience/expiry/nbf/subject를 검증한다. issuer+subject의 안정적인 해시를 기존 userId에 저장하고 모든 REST/terminal 진입점에서 권한을 확인한다. 런타임에 개발 인증 fallback은 없다.

**Tech Stack:** Go, coreos/go-oidc v3, Kubernetes v1alpha1 CRD 유지.

**Spec:** 사용자 Production Readiness Engineering 요구사항; `docs/PRODUCTION_REQUIREMENTS.md`, `docs/RELEASE_CRITERIA.md`.

## Global Constraints

- main 수정/직접 배포/자동 병합 금지. 작업 기준 origin/main `bc98d80` (참조 `60745d4` 이후).
- 실제 upstream key는 내부 model proxy만 보유한다.
- Mock/JWKS fixture 검증을 실제 IdP/cluster 검증으로 표현하지 않는다.
- 이번 단위에 포함되지 않는 CLI device login/refresh, IdP revocation, 조직 RBAC는 P0-1 잔여 항목으로 유지한다.

## Review Focus

- JWT 서명이 유효해도 잘못된 audience/issuer, 빈 sub, 누락 exp, 미래 nbf는 거부한다.
- 같은 sub라도 issuer가 다르면 소유권이 달라야 하고 label 길이가 유효해야 한다.
- JWKS 회전/동시 검증/의존성 실패 시 fail closed여야 한다.
- 인증 설정 누락 시 서버 시작 실패 및 직접 생성한 Server에서도 인증 거부.
- REST뿐 아니라 WebSocket upgrade와 연결 중 만료/소유권 변경도 차단한다.

## Task 1: 재검증·의존성 백로그

- [x] 필수 문서를 순서대로 읽고 최신 원격/기존 PR/테스트 기준선을 확인한다.
- [ ] `docs/PRODUCTION_BACKLOG.md`에 P0/P1/P2별 현재 코드 근거·잔여 위험·종료 증거를 작성한다.
- [ ] ADR-007에 JWT 선택·소유권 마이그레이션·운영 실패 모드를 기록한다.

## Task 2: JWT 검증기와 API 인증·인가

Files: `internal/auth/{oidc.go,oidc_test.go}`, `internal/api/{server.go,server_test.go}`, `internal/terminal/gateway.go`, `cmd/cask-api/main.go`, `go.mod`, `go.sum`.

Interfaces: `auth.Authenticator.Authenticate(context.Context,string) (auth.Identity,error)`; `auth.NewOIDC(context.Context,auth.Config) (*auth.OIDC,error)`; `auth.Identity{UserID,Issuer,Subject,ExpiresAt}`. 테스트용 임의 토큰 인증은 `_test.go` 안에만 둔다.

- [ ] 실패 테스트: 미설정 서버/임의 Bearer/user:xxx는 401, 유효 JWT는 201, 타인 GET/DELETE/terminal은 403.
- [ ] `go test ./internal/auth ./internal/api`로 RED를 확인한다.
- [ ] HTTPS JWKS, RS256/ES256 allowlist, issuer/audience/expiry/nbf/subject, 필수 scope를 구현한다. scope 부족은 403, 유효하지 않은 credential은 401.
- [ ] issuer+sub 해시 소유권, 감사 JSON 로그(토큰/원시 claims 없음), list 재필터링, terminal 사전 인가/만료 종료를 구현한다.
- [ ] 검증/회전/동시성/IdP 장애/권한/누출 테스트 GREEN 확인.
- [ ] 단위별 검증 후 커밋한다.

## Task 3: 배포 설정과 호환성·검증 문서

Files: `charts/agentcask/{values.yaml,templates/cask-api-deployment.yaml}`, `deploy/kind/cask-api.yaml`, `test/e2e/e2e_test.go`, `docs/{API_SPEC.md,SECURITY_MODEL.md,RUNBOOK.md}`, chart README.

- [ ] Helm에 필수 issuer/audience/JWKS 설정 및 렌더 실패 검증을 추가한다. 인증 우회 플래그를 추가하지 않는다.
- [ ] kind도 동일 검증기를 사용하도록 설정하고 E2E는 명시적으로 공급된 JWT를 사용한다. 토큰이 없으면 실제 E2E 실행은 실패하며 성공으로 집계하지 않는다.
- [ ] 레거시 세션 마이그레이션/토큰 갱신의 현재 한계/JWKS 회전·장애 대응을 문서화한다.
- [ ] `make test`, race, vet, build, Helm positive/negative, 가능한 cluster 검증을 실행하고 미실행 사유를 기록한다.
- [ ] 독립 리뷰 후 커밋/푸시/PR 생성. main/워크트리 연결 재확인. 사용자 승인 전 머지하지 않는다.
