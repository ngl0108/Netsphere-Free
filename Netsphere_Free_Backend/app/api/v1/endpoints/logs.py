from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.device import EventLog
from typing import List, Optional
from app.schemas.device import LogResponse
from app.api import deps
from app.models.user import User
from datetime import datetime, timedelta
from app.services.pii_masking_service import PiiMaskingService

router = APIRouter()

@router.get("/recent", response_model=List[LogResponse])
def get_recent_logs(
    skip: int = 0,
    limit: int = 1000, # 로그 양이 많을 수 있으니 여유있게 설정
    severity: Optional[str] = None,
    days: int = 7,     # 프론트에서 넘어오는 날짜 범위 (기본값 7일)
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    # 1. 기본 쿼리 생성 (최신순 정렬) + Device 관계 로딩
    query = db.query(EventLog).options(joinedload(EventLog.device)).order_by(EventLog.timestamp.desc())

    # 2. 날짜 필터링 로직 (핵심: 요청받은 days만큼만 계산해서 가져옴)
    if days > 0:
        cutoff_date = datetime.now() - timedelta(days=days)
        query = query.filter(EventLog.timestamp >= cutoff_date)

    # 3. 심각도 필터링 로직 (Warning, Error 등)
    if severity and severity.lower() != 'all':
        query = query.filter(EventLog.severity == severity.lower())

    # 4. 페이징 처리 및 결과 반환
    logs = query.offset(skip).limit(limit).all()
    policy = PiiMaskingService.get_policy(db)

    # [NEW] Device name 매핑
    result = []
    for log in logs:
        result.append(LogResponse(
            id=log.id,
            device_id=log.device_id,
            device=log.device.name if log.device else "Unknown",
            severity=log.severity,
            event_id=log.event_id,
            message=PiiMaskingService.mask_text(log.message, policy),
            source=PiiMaskingService.mask_text(log.source, policy),
            timestamp=log.timestamp
        ))
    return result
