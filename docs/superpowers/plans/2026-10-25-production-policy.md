# Production 개발 정책 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MVP 전용 금지·축소 규칙을 해제하고 보안 불변 조건, 현재 구현, 목표 요구사항, Production 출시 증거를 일관되게 구분한다.

**Architecture:** Go 핵심 서비스와 AgentSession CRD를 기존 자산으로 유지한다. 기존 배포 형태는 현재 구현 설명으로 보존하고, 변경 가능한 구조와 보안 경계는 분리한다. 기존 `docs/DESIGN_DECISIONS.md`를 ADR 관리 문서로 사용하며 별도 중복 ADR 인덱스는 만들지 않는다.

**Tech Stack:** Markdown 문서, 기존 Go 테스트와 kind/Helm 검증 도구. 런타임 코드·API·CRD·배포 설정 변경 없음.

**Spec:** 사용자의 「AgentCask — MVP 제약 제거 및 정식 제품 개발 정책 전환」 요청. 이 계획은 해당 요청을 실행 가능한 문서 변경 단위로 나눈다.

## Global Constraints

- 실제 upstream 모델 키를 Agent Pod, AgentSession, 사용자 응답, 터미널 또는 로그에 노출하지 않는다.
- 사용자·세션 인증/인가, 최소 권한 RBAC, 실행·데이터·네트워크 격리를 유지하거나 강화한다.
- 사용자에게 무제한 Kubernetes API 접근 권한을 제공하지 않는다. 기존 제품 클라이언트의 직접 Kubernetes/Pod 접근 금지도 유지한다.
- Web UI, 조직/권한 관리, Quota/Billing, 보안 통합, HA, 복수 런타임 등은 요구사항에 따라 도입 가능하며 이번 작업에서 구현하지 않는다.
- Go 기반 핵심 서비스, Kubernetes CRD, 기존 API 및 CRD 호환성을 기본 자산으로 유지한다.
- 현재 미구현 기능을 구현 완료 또는 Production Ready로 표시하지 않는다.
- Mock/Fake/Stub 및 kind plumbing 성공을 실제 서비스·격리·복구 검증의 대체 증거로 사용하지 않는다.
- 기본 디렉토리는 main으로 유지하고 전용 워크트리에서만 수정한다. 사용자 로컬 메모리와 다른 작업의 변경은 수정하지 않는다.

## Review Focus

1. 다른 문서의 오래된 금지 문구 때문에 Production 기능 구현을 거부하지 않도록 전체 추적 파일을 재검색한다.
2. 구조 완화를 이유로 upstream 자격 증명 경계나 기본 비공개 네트워크를 약화하지 않도록 문장 단위로 검토한다.
3. 예시·설계·현재 코드 지원 여부를 구분한다. enum 나열이나 런타임 이미지에 도구가 있다는 이유로 실제 통합 지원을 주장하지 않는다.
4. 과거 단계별 테스트 통과와 Production 출시 승인을 분리하고 미실행 검증은 미실행으로 기록한다.
5. 기존 kind 클러스터명 `agentcask-mvp` 등 호환성 식별자는 단어 정리를 위해 변경하지 않는다.

## 실행 상태 (2026-10-25)

이 절이 현재 진행 상태의 기준이다. 아래 Task 1–4의 개별 체크박스는 승인 당시 계획의 원문을 보존한 것으로, 미구현 목록으로 해석하거나 이미 끝난 작업을 재실행하지 않는다.

- [x] 사용자 승인 및 명시적 머지 요청 수신.
- [x] Task 1: 개발 규칙·PRD 전환, Production 요구사항/출시 기준 작성.
- [x] Task 2: 아키텍처·계약·보안 문서/ADR 전환, Production 로드맵 작성.
- [x] Task 3: README/과거 문서 팩/테스트/운영/차트 안내 정합성 수정.
- [x] Task 4 검증: `make test`, `make build`, `make runtime-test`, Helm lint/template, CI 옵션 Kustomize, 전용 클러스터 `make kind-test` 통과.
- [x] Markdown 24개 상대 링크 및 문서 전용 변경 확인. 잔여 MVP 표현은 역사·해제 설명·호환성 식별자로 분류.
- [x] 독립 리뷰: Critical/Important 없음. 계획의 오래된 실행 상태 지적은 이 상태 절과 하단 설명을 갱신하여 반영.
- [ ] 커밋·push·PR·머지: 위 검증 후 진행하며 실제 결과와 URL은 Git 이력/PR을 최종 기록으로 삼는다. 이 체크박스는 머지 전 작성 시점의 상태다.

## 진행 기준선

- [x] 원격 fetch 후 기본 main과 origin/main의 동일 커밋 확인: `8d48bef0fe04472fc08f30fc93638f3c995eb73a`.
- [x] 전용 워크트리 생성: `production-development-policy`.
- [x] 필수 문서 읽기 순서에 따라 조사하고 추적 Markdown 전체에서 제한 규칙 검색.
- [x] 기준선 `make test` 통과. kind/runtime opt-in E2E 실행 증거는 아님.
- [x] 사용자 계획 승인 및 머지 승인.

## Task 1: 개발 규칙과 정식 제품 요구사항

**Files:** `AGENTS.md`, `CLAUDE.md`, `PRD.md`; 생성 `docs/PRODUCTION_REQUIREMENTS.md`, `docs/RELEASE_CRITERIA.md`.

**문서 계약:** PRD는 제품 목적·사용자 흐름·현재 제공 범위를, Production Requirements는 목표 요구사항을, Release Criteria는 필수 검증 증거를 소유한다. AGENTS/CLAUDE는 해당 기준을 참조하고 중복된 축소 규칙을 두지 않는다.

- [ ] 현재 위반 사례를 목록화한다: Web UI 금지, gateway 결합 강제, minimal proxy, 조직·Quota·Billing·보안 기술 제외, kind만으로 완료 선언.
- [ ] AGENTS/CLAUDE에서 해당 금지 규칙을 요구사항·ADR 기반 선택으로 바꾸고 기존 이름과 보안/격리 규칙은 보존한다.
- [ ] PRD의 Non-goals를 영구 보안 제약과 이번 정책 작업의 비목표로 분리한다. CLI/OpenCode는 현재 기본값이며 영구 우선순위가 아님을 명시한다.
- [ ] Production Requirements에서 모든 기능에 필요한 품질/보안 역량과 요구사항에 따라 선택할 제품 기능·기술을 분리한다. 특정 보안 제품이나 Billing 자체를 무조건 출시 필수로 만들지 않는다.
- [ ] Release Criteria에 실제 시나리오, 인증/인가·위협 모델, 실패/복구, 다중 사용자/세션, 자동화, API 계약, 관측성, 확장/유지보수, 재현 배포, 공식 운영 문서, 성능/자원 기준을 정의한다.
- [ ] 각 출시 기준은 목표/허용치, 환경/버전, 실행 결과, 근거 링크, 책임자를 기록하도록 한다. 수치가 없는 성능·복구 항목은 미충족으로 다루며 임의 수치를 만들어 채우지 않는다.
- [ ] 보안 누출 금지와 격리 요구가 약화되지 않았는지 diff를 검토한다.

## Task 2: 아키텍처·계약·보안 문서와 로드맵

**Files:** `docs/ARCHITECTURE.md`, `docs/DESIGN_DECISIONS.md`, `docs/API_SPEC.md`, `docs/CRD_SPEC.md`, `docs/CLI_SPEC.md`, `docs/SECURITY_MODEL.md`, `docs/TERMINAL_GATEWAY.md`, `docs/CONTROLLER_DESIGN.md`, `docs/ISOLATION_PROFILES.md`, `docs/IMPLEMENTATION_PLAN.md`; 생성 `docs/PRODUCTION_ROADMAP.md`.

**문서 계약:** Architecture는 현재 구조와 허용된 확장 경계를, Design Decisions는 결정 상태/이유/영향/호환성을, Roadmap은 후속 작업·의존성·출시 증거를 소유한다. 기존 Implementation Plan은 초기 단계 이력/기준선이며 앞으로의 전체 제품 범위를 제한하지 않는다.

- [ ] 현재 구조와 목표 선택지를 구분한다. 독립 Terminal Gateway, provider별 gateway, 저장소, OIDC, Web UI/관리 포털, 이벤트 기반 controller, 동적 정책, 세션 영속화/복구, 복수 runtime, 멀티테넌시를 허용한다.
- [ ] 기존 CLI-only/no-portal 및 영구 gateway 결합 결정을 대체된 역사로 표시한다. 비공개 Agent Pod, profile 추상화, upstream 키 격리는 유지한다.
- [ ] 새 구조 결정에 기술적 근거, 보안 경계, 운영 비용, API/CRD 마이그레이션·롤백 영향, 결정 상태를 요구하는 ADR 양식을 기존 문서에 둔다.
- [ ] API/CRD/CLI의 현재 경로·스키마·명령과 default/kata 의미를 바꾸지 않는다. mock identity/dev token은 로컬 테스트 전용이며 Production 인증 증거가 아님을 명시한다.
- [ ] 격리 프로필 확장을 허용하되 실제 위협 모델에 맞는 런타임 검증이 필요하며 default나 가짜 RuntimeClass를 강한 격리 증거로 취급하지 않는다.
- [ ] 보안 모델에 세션/사용자 권한, 테넌트 간 자원·데이터 격리, 최소 RBAC, 기본 비공개 네트워크, 자격 증명 수명/철회, 비신뢰 코드 실행 통제를 명시한다. 구현 보장은 검증된 범위로만 기술한다.
- [ ] Production Roadmap을 보안/계약 → 복구/운영/확장 검증 → 요구사항별 제품 기능 확장으로 연결하고, 각 항목에 종료 증거와 현재 미검증 상태를 명시한다. 순서는 운영 위험·의존성에 따른 조정 가능 계획으로 둔다.
- [ ] 초기 계획의 stub/fake 성공 조건을 단계별 회귀 기준으로만 남기고 Production 완료 기준은 Release Criteria로 연결한다.

## Task 3: 진입 문서·운영·테스트 가이드 정합성

**Files:** `README.md`, `README copy.md`, `docs/TEST_PLAN.md`, `docs/KIND_TESTING.md`, `docs/CI_CD.md`, `docs/RUNBOOK.md`, `charts/agentcask/README.md`.

**문서 계약:** README는 현재 상태와 정식 기준 탐색의 출발점, Test Plan은 테스트 계층과 한계, Runbook은 현재 운영 절차와 출시 전 추가해야 할 운영 증거를 설명한다. `README copy.md`는 기존 내용을 임의 삭제하지 않고 역사적 문서 팩 안내로 축약·연결하여 별도 제품 규칙의 근원이 되지 않게 한다.

- [ ] README에 정책 전환과 현재 미검증 범위, 요구사항/로드맵/출시 기준 링크를 넣고 기존 사용·정리 명령은 보존한다.
- [ ] chart의 현재 노출 구성을 현재 기본값으로 설명하며 승인된 gateway/UI 추가의 금지로 읽히지 않도록 한다. dev token/로컬 이미지 예시는 Production 배포 가이드와 구분한다.
- [ ] Test Plan에 실제 다중 사용자·세션, 권한 부정 사례, 실제 runtime/provider, 장애 주입/복구, 부하·성능·자원, API/CRD 업그레이드·롤백 검증을 목표로 추가한다.
- [ ] kind/stub/fake RuntimeClass와 현재 CI가 증명하지 않는 항목을 명시한다. 기존 CI/CD 구성 또는 태그 발행이 Production 출시 승인을 자동으로 의미하지 않게 한다.
- [ ] Runbook에 운영자 전용 kubectl 접근, 장애·복구/백업 검증·관측성·용량·업그레이드 문서의 현황 및 추가 요구를 구분해 적는다. 없는 절차를 실행 가능한 것처럼 쓰지 않는다.
- [ ] 추적 파일 전체의 MVP 및 동의어 검색 결과를 현재 구현/역사/호환성 식별자/남은 금지 규칙으로 분류해 마지막 범주를 제거한다.

## Task 4: 검증·자체 검토·커밋·PR

- [ ] Markdown 상대 링크와 문서 역할/교차 참조를 확인한다. 새 파일을 포함해 보안·품질 기준과 충돌하는 문장이 없는지 자체 검토한다.
- [ ] `git diff --check`, `make test`, `make build`를 실행한다. 통과한 명령과 skip된 테스트를 구분해 기록한다.
- [ ] 도구/컨테이너 환경이 제공되면 `make helm-lint`, `make helm-template`, `kubectl kustomize deploy/kind`, `make kind-test`를 실행한다. 환경 실패 또는 미실행은 구체적으로 보고하고 통과로 표시하지 않는다.
- [ ] `git diff --stat`와 파일 목록을 검토하여 Go 코드·CRD·배포 설정·Makefile 변경이 없음을 확인한다. 변경 전후 테스트 목적/한계 설명이 일관되는지 확인한다.
- [ ] 자체 검토에서 요청의 6개 완료 조건을 각각 확인하고 결과를 PR 본문에 기록한다.
- [ ] 검증 후 문서 변경을 커밋하고 push한 뒤 PR을 생성한다. 권한 또는 검증 장애는 숨기지 않고 보고한다.
- [ ] 기본 디렉토리의 `git status --short --branch`, `git worktree list`와 작업 워크트리 상태를 재확인한다. 기존 `.serena/` 등 다른 작업의 파일을 건드리지 않는다.
- [ ] PR URL과 실제 검증 결과를 보고하고 명시적 머지 승인을 요청한다. 승인 전 병합/자동 병합 예약은 하지 않는다.

## 계획 자체 검토

- 사용자 요청 1·2는 Task 1/2, 요청 3은 Task 1/3, 요청 4는 Task 2, 요청 5는 Task 1–3, 요청 6은 Task 4에 대응한다.
- 새 문서 3개는 요구사항·로드맵·출시 증거로 책임이 다르다. ADR은 기존 문서를 재사용한다.
- 테스트 대상 동작을 바꾸지 않는 문서 작업이므로 런타임 구현 또는 문구 전체를 고정하는 취약한 테스트는 추가하지 않는다. 문서 정합성 검토와 기존 회귀 테스트로 검증한다.
- 이 계획은 승인 후 문서 변경과 검증이 실행되었다. 세부 실행 상태는 상단 상태 절을, 최종 커밋·PR·머지 결과는 Git 이력과 PR을 참조한다. Production 기능 구현 완료 보고가 아니다.
