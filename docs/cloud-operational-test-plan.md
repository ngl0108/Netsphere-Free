# 클라우드 운영 검증 테스트 플랜 (프리티어, 온프레미스 없음)

## 1. 범위

- 계획 기간: 2026-02-27 ~ 2026-03-31
- 컨트롤러: NetSphere v2.5.x
- 환경 제약:
  - 온프레미스 장비 없음
  - AWS/GCP/Azure 프리티어 계정 사용 가능
- 사인오프 목표:
  - Northbound 72시간 Soak 증빙
  - 30일 KPI 실측 증빙(MTTD/MTTR/자동조치 및 핵심 KPI 게이트)
  - ITSM/SIEM 커넥터 스테이징→운영 인증 런북 사인오프

## 2. 테스트 토폴로지 청사진

안정 신호 + 변동(churn) 신호를 만들기 위해 각 클라우드에 "상시 노드" 1개와 "에페메럴 노드" 1개를 둡니다.

| Provider | Site ID | Region | Network | Always-On Node | Ephemeral Node |
|---|---|---|---|---|---|
| AWS | aws_hq | us-east-1 | VPC 10.10.0.0/16, 서브넷 2개 | aws-core-1 | aws-edge-ephemeral |
| GCP | gcp_hq | us-central1 | VPC 10.20.0.0/16, 서브넷 2개 | gcp-core-1 | gcp-edge-ephemeral |
| Azure | azr_hq | eastus | VNet 10.30.0.0/16, 서브넷 2개 | azr-core-1 | azr-edge-ephemeral |

태그 규칙(전 Provider 공통):

- `nm_site` (aws_hq/gcp_hq/azr_hq)
- `nm_role` (core/edge)
- `nm_env` (staging)
- `nm_owner` (team 또는 user)
- `nm_trace_id` (run id)
- `nm_test_ttl` (yyyy-mm-dd)

## 3. 클라우드 리소스 구축 가이드

### AWS

1. VPC, 서브넷 2개, 라우트 테이블, 보안그룹 기본 구성을 생성합니다.
2. `aws-core-1`을 상시 실행 VM으로 생성합니다.
3. `aws-edge-ephemeral`을 생성하고 시작/중지 스케줄을 설정합니다.
4. 기본적으로 고비용 리소스는 피합니다: NAT Gateway, 관리형 VPN, 과도한 Public IPv4.

### GCP

1. 커스텀 VPC, 서브넷 2개, 방화벽 기본 구성을 생성합니다.
2. `gcp-core-1`은 Always Free 적용 가능 리전에서 상시 실행합니다.
3. `gcp-edge-ephemeral`은 테스트 시간대에만 사용합니다.
4. 예산 알림과 네트워크 egress 가드레일을 적용합니다.

### Azure

1. Resource Group, VNet, 서브넷 2개, NSG 기본 구성을 생성합니다.
2. `azr-core-1`을 상시 실행합니다.
3. `azr-edge-ephemeral`은 테스트 시간대에만 사용합니다.
4. 비용 예산 알림을 켜고 유휴 리소스를 자동/수동으로 종료합니다.

## 4. NetSphere 연동 설정

1. Cloud Accounts 페이지에서 클라우드 계정 3개를 등록합니다.
2. 계정 Preflight 체크 통과를 확인합니다.
3. 클라우드 Discovery Pipeline을 실행합니다.
4. 토폴로지 필터를 확인합니다:
   - Provider
   - Account
   - Region
5. 정규화된 리소스가 노출되는지 확인합니다:
   - Network(VPC/VNet/Subnet)
   - Compute(VM)
   - 지원되는 범위의 보안/라우트 엔티티

## 5. 테스트 시나리오

### A. Discovery + 토폴로지 반영

1. Provider별 및 Global Discovery를 실행합니다.
2. 첫 지도 생성 시간과 반영 완전성을 검증합니다.
3. 에페메럴 노드를 하루 2~3회 on/off 토글합니다.
4. 중복 없이 토폴로지가 업데이트되는지 확인합니다.

기대 증빙:

- Discovery Job 및 소요 시간
- 토폴로지 노드/링크 diff
- Candidate Queue 증감

### B. 중복 제거 + 저신뢰 Candidate Queue

1. Provider 간 유사한 이름/태그 패턴을 의도적으로 생성합니다.
2. 일부 리소스에 불완전 메타데이터를 주입합니다.
3. 저신뢰 항목이 자동 승격되지 않고 큐로 분류되는지 확인합니다.
4. 후보 승인/반려 후 토폴로지 반영 동작을 검증합니다.

기대 증빙:

- Candidate Queue 추이
- 오탐(False positive) 비율
- 승인 Trace 연결성

### C. 클라우드 Bootstrap + 안전 변경 엔진

1. Bootstrap 템플릿 Dry-run을 실행합니다.
2. 클라우드별 1노드 기준 Wave 롤아웃을 실행합니다.
3. 통제된 실패 1건(에페메럴 노드의 잘못된 bootstrap payload)을 주입합니다.
4. Post-check 실패 시 롤백이 트리거되는지 확인합니다.

기대 증빙:

- Dry-run/Wave/Rollback 실행 로그
- Approval ID <-> Execution ID Trace
- 롤백 지연시간(P95)

### D. Intent + Closed-Loop

1. `cloud_policy` Intent를 먼저 시뮬레이션 모드로 적용합니다.
2. 정책 Drift(태그/룰 위반)를 주입합니다.
3. Closed-loop가 조치를 평가하고 승인 게이트 정책을 준수하는지 확인합니다.
4. 조치/알림 Trace가 생성되는지 확인합니다.

기대 증빙:

- Intent validate/simulate/apply 결과
- Drift 탐지 로그
- 자동조치 vs 운영자 개입 건수

### E. Northbound ITSM/SIEM 72시간 Soak

1. 커넥터 모드를 순환하며 Soak를 실행합니다:
   - jira
   - servicenow
   - splunk
   - elastic
2. 로컬 리시버 또는 스테이징 엔드포인트에서 서명 검증을 강제합니다.
3. 주기적 실패 주입으로 retry/backoff 동작을 검증합니다.

기대 증빙:

- 72시간 성공률
- attempts P95
- failed_24h
- 서명 유효율

## 6. 운영 실행 명령

### 6.1 72시간 Soak

```bash
python Netsphere_Free_Backend/tools/run_northbound_soak_verification.py \
  --base-url http://localhost:8000 \
  --login-username "<admin>" \
  --login-password "<password>" \
  --duration-hours 72 \
  --interval-seconds 120 \
  --modes jira,servicenow,splunk,elastic \
  --use-local-receiver \
  --local-receiver-host host.docker.internal \
  --local-receiver-port 18080 \
  --local-receiver-fail-every 10 \
  --local-receiver-enforce-signature \
  --webhook-secret "soak-secret" \
  --min-success-rate-pct 95 \
  --max-attempts-p95 3 \
  --max-failed-24h 5 \
  --min-signature-valid-rate-pct 100 \
  --latest-json-path docs/reports/northbound-soak-72h-latest.json \
  --latest-md-path docs/reports/northbound-soak-72h-latest.md \
  --fail-on-threshold
```

### 6.2 30일 KPI Readiness

```bash
python Netsphere_Free_Backend/tools/export_kpi_readiness_report.py \
  --base-url http://localhost:8000 \
  --token "<token>" \
  --discovery-days 30 \
  --require-sample-minimums \
  --sample-min-discovery-jobs 30 \
  --sample-min-change-events 60 \
  --sample-min-northbound-deliveries 500 \
  --sample-min-autonomy-issues-created 20 \
  --sample-min-autonomy-actions-executed 20 \
  --latest-json-path docs/reports/kpi-readiness-30d-latest.json \
  --latest-md-path docs/reports/kpi-readiness-30d-latest.md \
  --fail-on-unhealthy
```

## 7. 수용 게이트(Acceptance Gates)

### Soak 게이트

1. `success_rate_pct >= 95`
2. `attempts_p95 <= 3`
3. `failed_24h <= 5`
4. `signature_valid_rate_pct >= 100`

### KPI 게이트

1. Plug and Scan:
   - first map P50이 목표 이내
   - auto reflection rate가 목표 이내
   - false positive rate가 목표 이내
2. Safe change:
   - 변경 성공률이 목표 이내
   - rollback P95가 목표 이내
3. Intent/Autonomy:
   - MTTD/MTTR 추세 개선이 측정 가능
   - auto-action/운영자 개입률이 충분한 샘플 수로 집계됨

## 8. 비용 및 안전 가드레일

1. 각 클라우드에 예산/알림(50/80/95%)을 강제합니다.
2. 테스트 시간 외에는 에페메럴 VM을 자동 중지합니다.
3. 모든 테스트 리소스에 TTL 태그를 필수 적용합니다.
4. 고아 리소스(Public IP, Disk, Snapshot, Load Balancer)를 매일 정리합니다.
5. 테스트 payload에 운영용 비밀정보를 사용하지 않습니다.

## 9. 산출물

- `docs/reports/northbound-soak-72h-latest.json`
- `docs/reports/northbound-soak-72h-latest.md`
- `docs/reports/kpi-readiness-30d-latest.json`
- `docs/reports/kpi-readiness-30d-latest.md`
- 일일 실행 로그 및 이슈 노트

## 10. 종료 기준

아래 3개를 모두 만족해야 플랜 사인오프 완료입니다.

1. 72시간 Soak 리포트가 임계값을 통과한다.
2. 30일 KPI Readiness 리포트가 최소 샘플 조건을 만족한 accepted 상태다.
3. Connector 인증 런북 체크리스트가 완료 및 승인되었다.
