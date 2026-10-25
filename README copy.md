# agentcask Documentation Pack — 과거 진입 문서

이 파일은 초기 MVP 문서 팩의 진입점이었다. 당시의 Web UI, 조직·billing, 보안 통합, 고급 gateway, 감사 파이프라인 등 제외 목록은 더 이상 개발 제한으로 유효하지 않다. 중복된 제품 규칙을 유지하지 않고 아래 공식 문서로 연결한다.

- 현재 구성·사용법: [README](README.md)
- 개발 규칙: [AGENTS](AGENTS.md), [CLAUDE](CLAUDE.md)
- 제품 목적·흐름: [PRD](PRD.md)
- 목표 요구사항: [Production Requirements](docs/PRODUCTION_REQUIREMENTS.md)
- 후속 작업: [Production Roadmap](docs/PRODUCTION_ROADMAP.md)
- 완료 증거: [Release Criteria](docs/RELEASE_CRITERIA.md)
- 결정 이력과 ADR: [Design Decisions](docs/DESIGN_DECISIONS.md)
- 보안 경계: [Security Model](docs/SECURITY_MODEL.md)
- 테스트 목적과 한계: [Test Plan](docs/TEST_PLAN.md)

초기 팩의 Go 서비스/AgentSession/CLI/kind 자산은 유지한다. 과거 제외 규칙의 해제가 현재 기능의 Production 준비 완료를 뜻하지 않는다. upstream 키의 Agent Pod·CRD·사용자 출력·로그 노출 금지와 내부 model proxy 자격 증명 경계는 변하지 않는다.
