# Cisco + 멀티클라우드 출시 사인오프 테스트 플랜 (운영 실측)

이 문서는 **실장비는 Cisco 중심**, 클라우드는 이미 연동된 **AWS/GCP/Azure/NCP** 기준으로,
출시 전 운영 사인오프를 완료하기 위한 상세 실행 절차입니다.

## 1. 목표와 완료 기준

### 1.1 목표

1. 장애/재시도/롤백 로그를 72시간 연속으로 자동 수집해 안정성 증빙 확보
2. KPI(성공률, MTTD/MTTR, 자동조치율 등) 일 단위 스냅샷 30~31일 누적
3. 종료 시 JSON/MD 리포트 + 로그 + 요약표로 출시 사인오프 판단 가능 상태 확보

### 1.2 완료(Definition of Done)

아래 3가지를 모두 만족하면 운영 사인오프 완료로 판단합니다.

1. `northbound-soak-72h-latest` 리포트가 임계치 통과
2. `kpi-readiness-30d-latest` 리포트가 샘플 최소치 포함 임계치 통과
3. Cloud/On-Prem 핵심 체인(Discovery -> Approval -> Reflection -> Change/Rollback) 증적 로그가 날짜별로 정리

---

## 2. 현재 기준 자산과 최소 추가 자원

### 2.1 현재 기준 자산(사용자 환경)

- 온프렘: Cisco 장비 다수(코어/액세스/WLC 포함)
- 클라우드 계정: `aws-hq`, `gcp-hq`, `azure-hq`, `ncp-hq`
- 컨트롤러: NetSphere Docker 스택

### 2.2 테스트 신뢰도 확보를 위한 최소 추가 자원

아래가 없으면 "롤백/재시도" 샘플이 부족해 KPI 신뢰도가 떨어집니다.

| 영역 | 최소 권장 | 현재 상태에서 추가 필요 여부 |
|---|---|---|
| AWS | 상시 1대 + 에페메럴 1대 + 2번째 리전 에페메럴 1대 | 다중 리전 실증용 1대 권장 |
| GCP | 상시 1대 + 에페메럴 1대 | 에페메럴 1대 권장 |
| Azure | 상시 1대 + 에페메럴 1대 | 에페메럴 1대 권장 |
| NCP | 상시 1대 + 에페메럴 1대(다른 서브넷) | 에페메럴 1대 권장 |
| Cisco 온프렘 | 코어 1, 분배/액세스 1, 엣지/변동 노드 1 | 보유 장비로 충족 가능 |

주의: 비용 제어를 위해 에페메럴 노드는 테스트 시간 외 반드시 중지합니다.

---

## 3. 테스트 트랙(출시 필수)

### Track A. Discovery/Topology 정확도

- 범위: 온프렘 Cisco + 4개 클라우드
- 목적: 첫 지도 생성시간, 자동 반영률, 중복/오탐률 검증

### Track B. Candidate Queue/저신뢰 정책

- 목적: 저신뢰 항목 자동승인 제외 및 후보 큐 분류 체인 검증

### Track C. 안전한 변경 엔진

- 목적: dry-run -> approval -> live -> post-check -> rollback 체인 증빙

### Track D. 인증/세션/재시도 안정성

- 목적: 401/403/세션 갱신/백오프 후 복구 동작 검증

### Track E. Northbound 72h Soak

- 목적: Jira/ServiceNow/Splunk/Elastic 전송 성공률, 재시도 P95, 서명 검증

### Track F. KPI 30~31일 누적

- 목적: 출시용 KPI 최소 샘플 충족 + 추세 안정화

---

## 4. 실행 일정 (D0~D31)

## D0 (오늘)

1. Docker 상태 고정
2. 테스트 대상 인벤토리 확정(Cisco/Cloud)
3. 증적 저장 폴더 생성
4. 자동 수집 태스크 등록(로그/KPI)

## D1~D3 (기능 체인 기준선)

1. Track A/B/C 기본 체인 1회 완주
2. 실패 유도 1건(의도적 잘못된 payload)으로 rollback 동작 확인
3. 후보 큐 분류 확인

## D4~D10 (장애/재시도/롤백 샘플 누적)

1. 클라우드 에페메럴 노드 on/off 일 2회
2. Cisco 대상 구성 변경 소규모 파동 배포(승인 포함)
3. 실패 원인 분류 라벨 점검

## D11~D13 (72h Soak)

1. Northbound 72시간 연속 실행
2. 중간 점검(24h, 48h) 결과 기록
3. 72h 종료 리포트 보관

## D14~D31 (KPI 누적)

1. 일 단위 KPI snapshot 고정
2. 주 단위(7일) 중간 리포트 생성
3. D30 또는 D31 최종 리포트/사인오프

---

## 5. 사전 준비 (Day 0 상세 절차)

### 5.1 Docker 상태 확인

```powershell
docker compose ps
```

확인 기준:

1. `backend`, `frontend`, `celery-worker`, `celery-beat`, `postgres`, `redis`가 Up
2. 에러 재시작 루프 없음

### 5.2 토큰 발급

```powershell
$body = "username=admin&password=Password1!!@"
$resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body
$token = $resp.access_token
if (-not $token -and $resp.data) { $token = $resp.data.access_token }
$env:NETSPHERE_TOKEN = $token
```

### 5.3 증적 저장 경로

```powershell
New-Item -ItemType Directory -Force -Path docs\reports\daily | Out-Null
New-Item -ItemType Directory -Force -Path docs\reports\soak | Out-Null
New-Item -ItemType Directory -Force -Path docs\reports\kpi | Out-Null
```

---

## 6. 테스트 케이스 상세 (핵심 14개)

각 테스트는 "실행 -> 통과기준 -> 증적" 3요소를 모두 남깁니다.

### TC-01 Discovery Global Baseline

- 실행:
  1. Cloud Accounts에서 4개 계정 `Validate`
  2. 각 계정 `Pipeline` 1회
  3. Auto Discovery에서 Cisco seed scan 1회
- 통과기준:
  1. 계정별 `status=ok`, failed=0
  2. 장비/토폴로지에 각 영역 노드가 노출
- 증적:
  - 계정별 pipeline 결과 캡처
  - `docs/reports/daily/<date>-tc01.md`

### TC-02 Provider/Account/Region 필터 동작

- 실행:
  1. Network Map에서 Provider/Account/Region 각각 변경
  2. 적용 즉시 노드 집합이 바뀌는지 확인
- 통과기준:
  1. 필터 선택 즉시 반영(지연 3초 이내)
  2. 빈 필터/전체 필터 회귀 없음
- 증적:
  - 화면 캡처 4장(각 provider)

### TC-03 저신뢰 파서 -> Candidate Queue

- 실행:
  1. 메타데이터 불완전 장비 1개 생성(태그/이웃정보 일부 누락)
  2. Discovery 실행
- 통과기준:
  1. 자동 반영 제외
  2. Candidate queue backlog 증가
- 증적:
  - Candidate panel 캡처
  - 관련 API 응답 스냅샷

### TC-04 Queue 승인/반려 -> 토폴로지 반영

- 실행:
  1. 후보 1건 승인, 1건 반려
  2. 토폴로지 재반영 확인
- 통과기준:
  1. 승인건만 반영
  2. 승인 ID 추적 가능
- 증적:
  - 승인 이력 + 토폴로지 diff

### TC-05 Cisco 변경 Dry-run

- 실행:
  1. Visual Config/Fabric/Template 중 1개 경로로 dry-run 실행
- 통과기준:
  1. diff 생성
  2. 위험 변경 경고 정확
- 증적:
  - dry-run 결과 JSON/스크린샷

### TC-06 Cisco Live 변경 + 승인 체인

- 실행:
  1. 승인 워크플로 생성
  2. live 변경 1건 실행
- 통과기준:
  1. Approval ID <-> Execution ID 연결
  2. post-check pass
- 증적:
  - 실행 trace 캡처

### TC-07 Rollback 유도

- 실행:
  1. 의도적 잘못된 payload 1건 투입
  2. rollback_on_failure=true로 실행
- 통과기준:
  1. post-check fail 감지
  2. 자동 rollback 트리거
  3. rollback latency 기록
- 증적:
  - `rollback` 로그 + KPI 카드

### TC-08 인증/세션 복구

- 실행:
  1. 토큰 만료 구간 유도(장시간 UI 유지)
  2. polling API 401 발생 구간 관찰
- 통과기준:
  1. 즉시 강제로그아웃 최소화
  2. 재로그인 또는 refresh 후 복구
- 증적:
  - 브라우저 콘솔/백엔드 access 로그

### TC-09 AWS 다중 리전 반영

- 실행:
  1. 보조 리전 에페메럴 노드 기동
  2. AWS pipeline 재실행
- 통과기준:
  1. 보조 리전 노드 반영
  2. 중복률 상승 없음
- 증적:
  - 리전 필터 캡처

### TC-10 GCP/Azure/NCP 기본 체인

- 실행:
  1. 각 provider pipeline
  2. 토폴로지 계층 노출 확인
- 통과기준:
  1. provider별 최소 1개 compute 노드 + 네트워크 노드
- 증적:
  - provider별 캡처

### TC-11 Northbound 72h Soak 시작

- 실행:

```powershell
python Netsphere_Free_Backend\tools\run_northbound_soak_verification.py `
  --base-url http://localhost:8000 `
  --login-username admin `
  --login-password "Password1!!@" `
  --duration-hours 72 `
  --interval-seconds 120 `
  --modes jira,servicenow,splunk,elastic `
  --use-local-receiver `
  --local-receiver-host host.docker.internal `
  --local-receiver-port 18080 `
  --local-receiver-fail-every 10 `
  --local-receiver-enforce-signature `
  --webhook-secret "soak-secret" `
  --min-success-rate-pct 95 `
  --max-attempts-p95 3 `
  --max-failed-24h 5 `
  --min-signature-valid-rate-pct 100 `
  --latest-json-path docs\reports\northbound-soak-72h-latest.json `
  --latest-md-path docs\reports\northbound-soak-72h-latest.md `
  --fail-on-threshold
```

- 통과기준:
  1. 스크립트 종료코드 0
  2. 4개 임계치 통과
- 증적:
  - `docs/reports/northbound-soak-72h-latest.*`

### TC-12 KPI 일일 Snapshot

- 실행(매일 1회):

```powershell
$headers = @{ Authorization = "Bearer $env:NETSPHERE_TOKEN" }
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/ops/kpi/readiness/snapshot?require_sample_minimums=true" -Headers $headers
```

- 통과기준:
  1. snapshot 저장 성공
  2. history에서 당일 데이터 확인
- 증적:
  - history 응답 저장

### TC-13 30일 KPI 리포트 추출

- 실행:

```powershell
python Netsphere_Free_Backend\tools\export_kpi_readiness_report.py `
  --base-url http://localhost:8000 `
  --token "$env:NETSPHERE_TOKEN" `
  --discovery-days 30 `
  --require-sample-minimums `
  --sample-min-discovery-jobs 30 `
  --sample-min-change-events 60 `
  --sample-min-northbound-deliveries 500 `
  --sample-min-autonomy-issues-created 20 `
  --sample-min-autonomy-actions-executed 20 `
  --latest-json-path docs\reports\kpi-readiness-30d-latest.json `
  --latest-md-path docs\reports\kpi-readiness-30d-latest.md `
  --fail-on-unhealthy
```

- 통과기준:
  1. `readiness.status=healthy`
- 증적:
  - `docs/reports/kpi-readiness-30d-latest.*`

### TC-14 사인오프 패키징

- 실행:
  1. 72h + 30d 최신 리포트 확인
  2. 주간/일간 로그 요약표 생성
  3. Go/No-Go 회의
- 통과기준:
  1. 치명 이슈 0
  2. KPI 기준 미달 없음
- 증적:
  - `docs/reports/release-signoff-<date>.md`

---

## 7. 로그 자동 수집 운영 방법

PowerShell 작업 스케줄러 또는 수동 일괄 실행(일 1회 권장):

```powershell
$date = Get-Date -Format "yyyyMMdd"
docker compose logs --since 24h backend > "docs/reports/daily/$date-backend.log"
docker compose logs --since 24h celery-worker > "docs/reports/daily/$date-celery-worker.log"
docker compose logs --since 24h celery-beat > "docs/reports/daily/$date-celery-beat.log"
```

필수 점검 문자열:

1. `rollback`
2. `retry`
3. `401` / `403`
4. `failed` / `exception`

---

## 8. KPI 일일 스냅샷 자동화(권장)

Celery 스케줄러 기본 snapshot 외에, 운영 증적 강화를 위해 수동 snapshot을 고정 시간(예: 매일 23:00) 1회 추가합니다.

권장 API:

1. `POST /api/v1/ops/kpi/readiness/snapshot`
2. `GET /api/v1/ops/kpi/readiness/history?days=30&limit=90`

---

## 9. Go / No-Go 판단 기준

### Go 조건

1. 72h Soak 임계치 통과
2. 30~31일 KPI readiness healthy
3. Cisco + 클라우드 핵심 체인 실패율 허용치 이내
4. 보안/권한/라이선스 치명 이슈 없음

### No-Go 조건

1. 자동 rollback 실패 1건 이상
2. 승인-실행 추적 끊김 발생
3. KPI가 샘플 부족 또는 critical
4. 세션 불안정으로 운영 연속성 저해

---

## 10. 오늘 바로 시작할 실행 순서 (실행형 요약)

1. D0 사전 준비 명령 실행(토큰/폴더/상태)
2. TC-01 ~ TC-04 수행 후 `docs/reports/daily/<date>-baseline.md` 작성
3. TC-05 ~ TC-07로 변경/롤백 체인 1회 완주
4. 문제 없으면 TC-11(72h soak) 시작
5. D+1부터 TC-12 일일 반복
6. D+30 또는 D+31에 TC-13/TC-14로 종료
