# NetSphere 운영 Runbook

이 문서는 “설명서(매뉴얼)” 중에서도, 운영자가 **서비스를 안전하게 배포/운영/장애대응/키교체**할 때 따라 할 수 있는 **실행 절차서**입니다.

## 1) 구성요소

- Backend (FastAPI + Uvicorn)
- Celery Worker (Discovery/Backup 등 백그라운드 작업)
- Celery Beat (스케줄 작업)
- PostgreSQL
- Redis (Celery broker)

## 2) 운영 전 체크리스트 (필수)

- **Secrets**
  - `FIELD_ENCRYPTION_KEY` 설정(필수, 분실 시 복구 불가)
  - `SECRET_KEY` 설정(JWT 서명용)
  - DB 계정/비밀번호 설정
- **환경변수**
  - `APP_ENV=production`
  - `LOG_FORMAT=json`
- **스토리지**
  - DB 볼륨/백업 정책 적용
  - `firmware_storage` 등 마운트 경로 확인

## 3) 필수 환경변수

- **DB/Redis**
  - `DATABASE_URL`
  - `REDIS_URL`
- **Security**
  - `FIELD_ENCRYPTION_KEY` (필수)
  - `SECRET_KEY` (필수)
- **Logging**
  - `LOG_LEVEL` (기본 INFO)
  - `LOG_FORMAT` (json|text, 기본 json)
  - `LOG_TO_FILE` (true|false, 기본 false)
  - `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` (선택)

## 4) 키 생성/주입 (FIELD_ENCRYPTION_KEY)

- 키 생성(운영 PC에서 1회 수행 후 안전 보관)
  - `python -m app.scripts.generate_field_encryption_key`
- 키 주입
  - docker-compose 사용 시: backend/celery-worker/celery-beat 모두 동일한 `FIELD_ENCRYPTION_KEY`를 주입
  - 운영 권장: 환경변수/Secret Manager로 주입(파일에 저장/커밋 금지)

## 5) DB에 평문/구키 데이터 정리(재암호화)

### 5.1 평문 → 암호화(1회 정리)

1) 드라이런(변경 예정 건수 확인)
   - `DRY_RUN=1 python -m app.scripts.reencrypt_credentials`
2) 실제 반영
   - `DRY_RUN=0 python -m app.scripts.reencrypt_credentials`

### 5.2 키 교체(구키 → 신키)

1) 신키를 먼저 운영 환경에 주입(서비스 재시작 전)
2) 드라이런
   - `OLD_FIELD_ENCRYPTION_KEY=<구키> DRY_RUN=1 python -m app.scripts.reencrypt_credentials`
3) 실제 반영
   - `OLD_FIELD_ENCRYPTION_KEY=<구키> DRY_RUN=0 python -m app.scripts.reencrypt_credentials`
4) 완료 후
   - 구키 폐기(보관 정책에 따름)
   - `OLD_FIELD_ENCRYPTION_KEY` 환경변수 제거

## 6) 배포/기동 절차 (docker-compose 기준)

1) `.env` 또는 운영 Secret 설정 준비
2) 컨테이너 기동
   - `docker compose up -d --build`
3) 헬스체크
   - Backend: `/` 또는 `/docs` 응답 확인
   - DB/Redis: 컨테이너 healthcheck 확인
4) 로그 확인
   - Backend/Celery Worker 로그에 에러 없는지 확인

## 7) 운영 중 점검 포인트

- **로그**
  - 기본 stdout(JSON) 로그 수집(권장: Loki/ELK)
  - 응답 헤더 `X-Request-ID`로 요청-로그 추적
- **DB**
  - 커넥션 풀 고갈/락/디스크 용량 모니터링
- **Redis**
  - 큐 적체/메모리 사용량 모니터링
- **Celery**
  - 워커 수, 동시성, 실패율/재시도율 모니터링

## 7.1) Phase 2: 워커 수평 확장(Discovery/백그라운드 작업)

docker-compose 기준으로 `celery-worker`는 수평 확장을 고려해 `container_name`을 사용하지 않습니다.

- 워커 확장 예시
  - `docker compose up -d --scale celery-worker=3`
- 동시성 튜닝(환경변수)
  - `CELERY_WORKER_CONCURRENCY`: 워커 프로세스 내 동시 실행 수
  - `CELERY_PREFETCH_MULTIPLIER`: 큐 프리패치(기본 1 권장, 작업 편중 완화)
  - `CELERY_LOGLEVEL`: 워커 로그 레벨
  - `CELERY_MAX_TASKS_PER_CHILD`: 워커 프로세스 재활용(메모리 누수 완화)
  - `CELERY_VISIBILITY_TIMEOUT`: Redis visibility timeout(acks_late 사용 시 재전달 기준)
  - `DISCOVERY_TASK_RATE_LIMIT`, `NEIGHBOR_CRAWL_RATE_LIMIT`, `SSH_SYNC_TASK_RATE_LIMIT`: 태스크별 레이트리밋
- 운영 팁
  - 대규모 스캔은 워커 수를 먼저 늘리고, 이후 concurrency를 조정하는 방식이 안전합니다.
  - DB/Redis가 병목이면 워커만 늘려도 효과가 제한될 수 있습니다.

## 7.2) Phase 2: 폭주(Storm) 대비

- **Syslog 폭주**
  - Backend는 UDP Syslog를 내부 큐로 받아 **Celery(syslog 큐)**로 넘겨 DB 저장을 워커로 분리합니다.
  - 튜닝(환경변수): `SYSLOG_QUEUE_SIZE`, `SYSLOG_WORKERS`, `SYSLOG_DROP_LOG_INTERVAL_SEC`, `SYSLOG_CELERY_QUEUE`, `SYSLOG_TASK_RATE_LIMIT`
- **Celery 폭주**
  - 디스커버리/네이버 크롤/SSH Sync는 큐를 분리하고 태스크별 레이트리밋을 적용합니다.
  - 증상: Redis 큐 적체, DB 쓰기 병목, 워커 CPU 100%
  - 조치: 워커 수평 확장 → 레이트리밋 강화 → DB/Redis 리소스 증설 순으로 접근

## 7.3) Phase 2: Syslog 워커 분리(권장)

Syslog 처리량이 중요한 환경에서는 `celery-worker`를 역할별로 분리하는 것이 안전합니다.

- 예시
  - 일반 워커: `CELERY_QUEUES=default,discovery,ssh,monitoring,maintenance`
  - Syslog 전용 워커: `CELERY_QUEUES=syslog`
  - docker-compose에서 `--scale celery-worker=N`으로 확장하거나, 별도 서비스로 분리 운영합니다.

## 7.4) Phase 4: Job 기반(비동기) 작업 운영

Long-running 작업은 API 타임아웃/워커 블로킹을 피하기 위해 Job(Celery)로 실행합니다.

- **Job 상태 조회**
  - `GET /api/v1/jobs/{task_id}`
  - 응답: `state`, `ready`, `successful`, `result` (실패 시 `error`)
- **VLAN 벌크 배포**
  - `POST /api/v1/devices/Netsphere_Free_Deploy/vlan` → `job_id` 즉시 반환
  - 큐: `ssh`
- **Compliance 스캔**
  - `POST /api/v1/compliance/scan` → `job_id` 즉시 반환
  - 큐: `maintenance`
- **자동 점검(스케줄)**
  - Config Drift: `app.tasks.compliance.run_scheduled_config_drift_checks` (매일 03:10)
  - Compliance Scan: `app.tasks.compliance.run_scheduled_compliance_scan` (매일 03:30)
  - 비활성화(SystemSetting):
    - `config_drift_enabled`: `0/false/no`면 스킵
    - `compliance_scan_enabled`: `0/false/no`면 스킵
    - `compliance_scan_standard_id`: 숫자면 해당 표준만 스캔
- **리포트 내보내기**
  - Inventory: `GET /api/v1/devices/{device_id}/inventory/export?format=xlsx|pdf`
  - Compliance: `GET /api/v1/compliance/reports/export?format=xlsx|pdf&device_id=<optional>`

## 8) 장애 대응(간단 절차)

- **API 5xx 증가**
  1) Backend 로그에서 `X-Request-ID`로 원인 추적
  2) DB/Redis 상태 확인
  3) 최근 배포/설정 변경(특히 키/환경변수) 롤백 검토
- **복호화 실패(값이 None으로 내려오는 증상)**
  - 원인: `FIELD_ENCRYPTION_KEY`가 기존 DB 암호문과 불일치
  - 조치:
    1) 올바른 키로 서비스 재기동
    2) 키 교체 중이었다면 `OLD_FIELD_ENCRYPTION_KEY`로 재암호화 수행
- **Discovery가 느리거나 멈춤**
  - 원인 후보: 워커 부족/큐 적체/DB 병목
  - 조치: 워커 수평 확장/동시성 조정/스캔 범위 축소

## 9) 백업/복구(권장)

- **DB 백업**: 매일 스냅샷 + 주기적 PITR(가능하면)
- **Secrets 백업**: `FIELD_ENCRYPTION_KEY`는 별도 보안 저장소에 2중 보관
- **복구 리허설**: 분기 1회 이상(실제 복구 가능성 검증)

## 10) Observability(모니터링)

- **목표**
  - Prometheus로 지표 수집(`/metrics`)
  - Grafana로 대시보드/로그 탐색
  - Loki+Promtail로 로그 중앙화(파일 로그 기반)
- **실행**
  - `docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build`
- **접속**
  - Backend metrics: `http://localhost:8000/metrics`
  - Prometheus: `http://localhost:9090`
  - Grafana: `http://localhost:3000` (기본: `admin/admin`, 환경변수로 변경 가능)
  - Loki: `http://localhost:3100`
