# NetSphere Free

NetSphere Free is the public entry point to the NetSphere platform.
It is designed as a discovery-first network operations workspace for teams that want to move from manual visibility to structured topology, sanitized data collection, and connected NMS workflows.

NetSphere Free는 NetSphere 플랫폼의 공개형 시작점입니다.
수동 점검 중심의 운영에서 벗어나 자동 탐지, 토폴로지 가시화, 정제된 데이터 수집, Connected NMS 흐름으로 넘어가고 싶은 팀을 위한 입문형 워크스페이스입니다.

## Why This Repository / 이 레포가 보여주는 것

- Multi-vendor auto discovery and inventory collection
- Auto topology and path visibility
- Connected NMS workflow with sanitized upload model
- Same-PC validation path for the Windows Free collector experience
- Public-safe documentation, test flow, and product positioning materials

## Quick Links / 바로가기

| Need | Link |
|---|---|
| Product overview / 제품 개요 | [docs/FEATURE_BROCHURE.md](docs/FEATURE_BROCHURE.md) |
| Free edition brochure / Free 소개 자료 | [docs/PREVIEW_BROCHURE.md](docs/PREVIEW_BROCHURE.md) |
| Documentation index / 문서 목차 | [docs/README.md](docs/README.md) |
| User guide / 사용자 가이드 | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Local collector quick start / 실행 방법 | [Netsphere_Free_Deploy/preview-collector-local/README.md](Netsphere_Free_Deploy/preview-collector-local/README.md) |
| Local testing guide / 로컬 검증 가이드 | [docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md](docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md) |
| Architecture / 아키텍처 | [docs/PREVIEW_COLLECTOR_ARCHITECTURE.md](docs/PREVIEW_COLLECTOR_ARCHITECTURE.md) |
| Discovery and topology runbook / 탐지·토폴로지 런북 | [docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md](docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md) |
| Contributor and sanitized upload guide / 업로드 기여 가이드 | [docs/PREVIEW_CONTRIBUTOR_GUIDE.md](docs/PREVIEW_CONTRIBUTOR_GUIDE.md) |
| Sales demo playbook / 데모 진행 자료 | [docs/SALES_DEMO_PLAYBOOK.md](docs/SALES_DEMO_PLAYBOOK.md) |

## What NetSphere Free Is For / 어떤 상황에 잘 맞는가

NetSphere Free is built for teams that need fast operational visibility before they are ready for a full private deployment.

NetSphere Free는 전체 사설 운영 환경을 바로 도입하기 전,
다음과 같은 가치를 먼저 경험하려는 팀에 잘 맞습니다.

- Discover devices without building a heavy NOC stack first
- Visualize topology before designing deeper automation policy
- Validate data collection and sanitization workflows safely
- Prepare internal demos, pilot reviews, and onboarding sessions

## Included in This Repository / 레포 구성

- `Netsphere_Free_Backend/`
- `Netsphere_Free_Frontend/`
- `Netsphere_Free_Deploy/`
- `preview-installer/`
- `scenario-lab/`
- `docs/`
- `tools/`

## Start in 3 Minutes / 3분 시작 가이드

### 1. Run the local Free runtime

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\up.ps1 -Build
```

### 2. Open the UI

- `http://127.0.0.1:18080`

### 3. Go deeper if needed

- Full runtime entry: [Netsphere_Free_Deploy/preview-collector-local/README.md](Netsphere_Free_Deploy/preview-collector-local/README.md)
- Local validation checklist: [docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md](docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md)
- User-facing workflows: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)

## Documentation Map / 문서 안내

### For readers who want the big picture / 전체 그림을 빠르게 보고 싶다면

- [docs/FEATURE_BROCHURE.md](docs/FEATURE_BROCHURE.md)
- [docs/PREVIEW_BROCHURE.md](docs/PREVIEW_BROCHURE.md)

### For users who want to operate the product / 실제 사용 흐름을 보고 싶다면

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- [docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md](docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md)

### For engineers who want setup and validation details / 설정과 검증 절차가 필요하다면

- [Netsphere_Free_Deploy/preview-collector-local/README.md](Netsphere_Free_Deploy/preview-collector-local/README.md)
- [docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md](docs/PREVIEW_COLLECTOR_LOCAL_TESTING.md)
- [docs/PREVIEW_INSTALL_TEST_CHECKLIST.md](docs/PREVIEW_INSTALL_TEST_CHECKLIST.md)
- [docs/PREVIEW_COLLECTOR_ARCHITECTURE.md](docs/PREVIEW_COLLECTOR_ARCHITECTURE.md)

### For stakeholder demos and positioning / 소개 자료와 데모 흐름이 필요하다면

- [docs/SALES_DEMO_PLAYBOOK.md](docs/SALES_DEMO_PLAYBOOK.md)
- [docs/PREVIEW_EXPERIENCE_POLICY.md](docs/PREVIEW_EXPERIENCE_POLICY.md)
- [docs/RUNTIME_DATA_BOUNDARIES.md](docs/RUNTIME_DATA_BOUNDARIES.md)

## Public Repository Policy / 공개 레포 정책

This repository is intentionally public.
Only Free-safe code, docs, and assets should live here.

이 레포는 의도적으로 공개 상태를 유지합니다.
따라서 Pro 전용 운영 자산, 민감한 내부 문서, 비공개 라이선스/배포 도구는 포함하지 않는 것이 원칙입니다.

## Related Repositories / 관련 레포

- Public Free edition: [ngl0108/Netsphere-Free](https://github.com/ngl0108/Netsphere-Free)
- Private Pro edition: `ngl0108/Netsphere-Pro`
- Private intake runtime: `ngl0108/Netsphere-Intake-Server`
