# NetSphere API Backend

이 디렉터리는 NetSphere의 FastAPI 백엔드입니다.

## 역할

- 장비 / 사이트 / 토폴로지 API
- Discovery / Sync / Bootstrap 실행
- 승인, 변경 실행, 롤백, 감사 이력
- 라이선스 / 권한 / 정책 가드
- KPI / 리포트 / 운영 검증 API

## 내부 경로

- `app/`: 애플리케이션 코드
- `tests/`: API, 계약, synthetic, driver 테스트
- `tools/`: 품질 게이트, KPI export, signoff 도구

## 참고

- 제품명은 `NetSphere`로 정리 중이지만, 하위 디렉터리 이름 `Netsphere_Free_Backend`는 도구와 경로 호환성을 위해 유지합니다.
