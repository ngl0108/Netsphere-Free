# Northbound 72h Soak Runbook

ITSM/SIEM 연동의 장기 안정성(재시도/서명 포함)을 72시간 기준으로 검증하는 실행 가이드입니다.

## 목적

- Connector 전송 성공률 장기 추적
- 재시도 정책(backoff/p95 attempts) 실측
- 서명(`X-NetManager-Signature-V2`) 유효성 검증
- 실패 원인/24h 실패량 점검

## 준비

- 관리자 토큰 준비 (`admin` 권한)
- NetSphere API 접근 가능 URL
- (권장) 스테이징 수신기 또는 로컬 검증 수신기

## 72시간 실행 예시 (로컬 수신기 포함)

```bash
python Netsphere_Free_Backend/tools/run_northbound_soak_verification.py \
  --base-url http://localhost:8000 \
  --token "<admin-token>" \
  --duration-hours 72 \
  --interval-seconds 60 \
  --modes jira,servicenow,splunk,elastic \
  --use-local-receiver \
  --local-receiver-host host.docker.internal \
  --local-receiver-port 18080 \
  --local-receiver-fail-every 10 \
  --local-receiver-enforce-signature \
  --webhook-secret "soak-secret" \
  --webhook-retry-attempts 3 \
  --webhook-retry-backoff-seconds 1 \
  --webhook-retry-max-backoff-seconds 8 \
  --webhook-retry-jitter-seconds 0.2 \
  --min-success-rate-pct 95 \
  --max-attempts-p95 3 \
  --max-failed-24h 5 \
  --min-signature-valid-rate-pct 100 \
  --output-dir docs/reports \
  --filename-prefix northbound-soak-72h \
  --latest-json-path docs/reports/northbound-soak-72h-latest.json \
  --latest-md-path docs/reports/northbound-soak-72h-latest.md \
  --fail-on-threshold
```

## 스테이징 ITSM/SIEM 엔드포인트로 실행 예시

```bash
python Netsphere_Free_Backend/tools/run_northbound_soak_verification.py \
  --base-url https://staging-netsphere.example.com \
  --token "<admin-token>" \
  --insecure \
  --duration-hours 72 \
  --interval-seconds 120 \
  --modes jira,servicenow,splunk,elastic \
  --jira-url "https://jira-stg.example.com/rest/api/2/issue" \
  --servicenow-url "https://snow-stg.example.com/api/now/table/incident" \
  --splunk-url "https://splunk-stg.example.com:8088/services/collector/event" \
  --elastic-url "https://elastic-stg.example.com/netsphere/_doc" \
  --webhook-secret "<shared-secret>" \
  --fail-on-threshold
```

## 통과 기준(권장)

- `success_rate_pct >= 95`
- `attempts_p95 <= 3`
- `northbound.totals.failed_24h <= 5`
- (로컬 수신기 검증 시) `signature_valid_rate_pct >= 100`

## 산출물

- 타임스탬프 리포트:
  - `docs/reports/northbound-soak-*.json`
  - `docs/reports/northbound-soak-*.md`
- 고정 리포트(옵션):
  - `docs/reports/northbound-soak-72h-latest.json`
  - `docs/reports/northbound-soak-72h-latest.md`
