# NetSphere Backend

Cisco 네트워크 장비를 관리하는 SDN(Software Defined Networking) 스타일의 백엔드 서버입니다.  
FastAPI를 기반으로 하며, Celery를 이용한 비동기 작업 처리, SNMP 모니터링, Syslog 수집, Config Pull/Push 기능을 제공합니다.

## 주요 기능 (Phase 1 ~ 2 완료 기준)

- 장비 등록 및 목록 관리
- SNMP 기반 실시간 상태 모니터링 (online/offline, CPU/Memory)
- Syslog 수집 및 이벤트 로그 저장/조회
- SSH를 이용한 Running Config Pull 및 파싱 (ConfigBackup 저장)
- Config Template 관리 (CRUD)
- 템플릿 기반 Config Push (비동기 Celery 태스크)
- Swagger UI를 통한 API 문서화 (`/docs`)

## 민감정보 암호화 설정 (필수)

장비 접속 정보(SSH/SNMPv3 Key 등)는 DB에 `enc:` 접두어가 붙은 **Fernet 암호문** 형태로 저장됩니다.

- `.env`에는 실제 운영 키를 커밋하지 않습니다(.gitignore 처리됨). 운영에서는 환경변수/Secret Manager로 주입하세요.
- 운영(Production)에서는 `FIELD_ENCRYPTION_KEY`를 반드시 별도로 설정해야 합니다(미설정 시 서버가 시작되지 않습니다).
- 키 생성:
  - `python -m app.scripts.generate_field_encryption_key`
- 기존 DB에 평문이 남아있거나, 암호화 키를 교체해야 할 때:
  - 평문 → 암호화: `DRY_RUN=0 python -m app.scripts.reencrypt_credentials`
  - 키 교체(구키 → 신규키): `OLD_FIELD_ENCRYPTION_KEY=<구키> DRY_RUN=0 python -m app.scripts.reencrypt_credentials`

## 로깅 설정 (권장)

기본 로그는 stdout(JSON)로 출력됩니다. 필요 시 파일 로테이션 로그를 추가로 활성화할 수 있습니다.

- 환경변수
  - `LOG_LEVEL` (기본: INFO)
  - `LOG_FORMAT` (json|text, 기본: json)
  - `LOG_TO_FILE` (true|false, 기본: false)
  - `LOG_FILE` (기본: 비활성, `LOG_TO_FILE=true`일 때만 기본값 logs/app.log 사용)
  - `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- 요청 추적
  - 모든 응답에 `X-Request-ID`가 포함되며, 로그에는 `request_id`, `path`, `method`가 자동으로 붙습니다.

## 파일 구조
Netsphere_Free_Backend/
├── app/
│   ├── init.py
│   ├── main.py                      # FastAPI 앱 초기화 및 lifespan
│   ├── api/
│   │   └── v1/
│   │       ├── router.py            # 메인 API 라우터
│   │       └── endpoints/
│   │           ├── devices.py       # 장비 관리 API
│   │           ├── config.py        # Config Pull/History/Deploy API
│   │           ├── logs.py          # Event Log 조회 API
│   │           └── config_template.py # Config Template CRUD API
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy Base (declarative_base)
│   │   ├── session.py               # DB 세션 관리
│   │   └── base_class.py            # (기존 Base 클래스 파일, 필요 시 통합)
│   ├── models/
│   │   ├── init.py
│   │   ├── device.py                # Device, ConfigBackup 모델
│   │   ├── log.py                   # EventLog 모델
│   │   └── config_template.py       # ConfigTemplate 모델
│   ├── schemas/
│   │   ├── device.py                # Device 관련 Pydantic 스키마
│   │   └── config_template.py       # ConfigTemplate 스키마
│   ├── services/
│   │   ├── ssh_service.py           # Netmiko 기반 SSH 연결 및 명령어 실행
│   │   ├── parser_service.py        # Config 파싱 로직
│   │   └── syslog_service.py        # Syslog UDP 서버 및 저장 로직
│   ├── tasks/
│   │   ├── init.py
│   │   └── config.py                # Celery 태스크 (pull_and_parse_config, deploy_config_task)
│   └── core/
│       └── config.py                # (향후 설정 관리용, 현재 미사용)
├── celery_app.py                    # Celery 앱 정의
├── requirements.txt                 # 의존성 목록
├── netmanager.db                    # SQLite 데이터베이스 (git ignore 권장)
└── README.md
text## 설치 및 실행 방법

1. **필수 요구사항**
   - Python 3.11 (권장)
   - Docker (Redis 컨테이너 사용)

2. **가상환경 생성 및 활성화**
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate   # Windows
   # source venv/bin/activate  # Linux/macOS

의존성 설치Bashpip install -r requirements.txt
Redis 컨테이너 실행Bashdocker run -d --name netsphere-redis -p 6379:6379 redis:alpine
서버 실행 (3개 터미널 필요)
터미널 1 (FastAPI 서버)Bashpython -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
터미널 2 (Celery Worker)Bashpython -m celery -A celery_app worker --pool=solo --loglevel=info
터미널 3 (Celery Beat - 주기적 모니터링)Bashpython -m celery -A celery_app beat --loglevel=info

API 문서 확인
브라우저에서 http://127.0.0.1:8000/docs 접속


테스트 방법

장비 등록: POST /api/v1/devices/
Config Pull: POST /api/v1/config/pull/{device_id}
Config Template 등록: POST /api/v1/config-templates/
Config Deploy: POST /api/v1/config/Netsphere_Free_Deploy/{device_id}/{template_id}
로그 조회: GET /api/v1/logs/

다음 단계 (Phase 3 예정)

프론트엔드 (React + Tailwind CSS) 개발
Topology Discovery (CDP/LLDP)
Advanced Validation 및 Rollback 기능
