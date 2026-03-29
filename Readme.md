# NetSphere Free

[![Website](https://img.shields.io/badge/Website-netsphereapp.com-0A66C2?style=for-the-badge)](https://netsphereapp.com/)
[![Docs](https://img.shields.io/badge/Docs-Explore%20Guides-1f883d?style=for-the-badge)](docs/README.md)
[![Launch](https://img.shields.io/badge/Launch-Open%20NetSphere%20Free-f59e0b?style=for-the-badge)](Netsphere_Free_Deploy/preview-collector-local/README.md)

NetSphere Free is the public entry point to the NetSphere platform.
It is designed as a discovery-first network operations workspace for teams that want to move from manual visibility to structured topology, sanitized data collection, and connected NMS workflows.

NetSphere Free는 NetSphere 플랫폼의 공개형 시작점입니다.
수동 점검 중심의 운영에서 벗어나 자동 탐지, 토폴로지 가시화, 정제된 데이터 수집, Connected NMS 흐름으로 넘어가고 싶은 팀을 위한 입문형 워크스페이스입니다.

## Visit The Homepage / 공식 홈페이지

**Explore NetSphere on the web:** [https://netsphereapp.com/](https://netsphereapp.com/)

**공식 홈페이지에서 NetSphere를 먼저 확인해보세요:** [https://netsphereapp.com/](https://netsphereapp.com/)

## Customer Launch Experience / 고객 실행 경험

Customers do not need to memorize a local IP address to open NetSphere Free.
The intended experience is:

- Launch `NetSphere Free` from the desktop or start menu shortcut
- Let the launcher start the local runtime automatically
- Open the browser without manually typing a URL

고객은 NetSphere Free를 열기 위해 로컬 IP 주소를 외울 필요가 없습니다.
권장 경험은 다음과 같습니다.

- 바탕화면 또는 시작 메뉴의 `NetSphere Free` 바로가기 실행
- 런처가 로컬 런타임을 자동으로 시작
- 사용자가 URL을 직접 입력하지 않아도 브라우저가 열림

## Why This Repository / 이 레포가 보여주는 것

- Multi-vendor auto discovery and inventory collection
- Auto topology and path visibility
- Connected NMS workflow with sanitized upload model
- Same-PC validation path for the Windows Free collector experience
- Public-safe documentation, test flow, and product positioning materials

## Quick Links / 바로가기

| Need | Link |
|---|---|
| Official homepage / 공식 홈페이지 | [netsphereapp.com](https://netsphereapp.com/) |
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

- `http://localhost:18080`

You normally should not need to type this manually because the launcher opens the browser for you.

보통은 런처가 브라우저를 자동으로 열어주므로 이 주소를 직접 입력할 필요가 없습니다.

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
