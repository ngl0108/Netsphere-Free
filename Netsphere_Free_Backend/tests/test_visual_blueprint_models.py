import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.visual_config import VisualBlueprint, VisualBlueprintVersion


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_visual_blueprint_versioning(db):
    b = VisualBlueprint(name="bp1", description="d", owner_id=1)
    db.add(b)
    db.flush()

    v1 = VisualBlueprintVersion(blueprint_id=b.id, version=1, graph_json={"nodes": [], "edges": []})
    db.add(v1)
    db.flush()
    b.current_version_id = v1.id
    db.commit()

    db.refresh(b)
    assert b.current_version_id == v1.id
    assert b.current_version.version == 1

    v2 = VisualBlueprintVersion(blueprint_id=b.id, version=2, graph_json={"nodes": [{"id": "n1"}], "edges": []})
    db.add(v2)
    db.flush()
    b.current_version_id = v2.id
    db.commit()

    db.refresh(b)
    assert b.current_version.version == 2
