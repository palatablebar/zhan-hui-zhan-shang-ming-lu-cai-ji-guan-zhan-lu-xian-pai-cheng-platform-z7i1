"""批次补录 HTTP 层单测：RBAC、上传登记、发布 SAVEPOINT 失败恢复、幂等、回滚接口。

用 SQLite + TestClient，覆盖真实路由/控制器/依赖装配，不依赖 MySQL。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.app import create_app
from src.config.database import get_db
from src.models import Base
from src.models.exhibitor import Exhibitor
from src.models.import_batch import ImportBatch
from src.services import exhibitor_service
from src.services.batch_import import importer
from src.utils.security import create_access_token

app = create_app()


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield maker
    engine.dispose()


@pytest.fixture()
def client(session_factory, monkeypatch):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # 不进入 with（不触发 lifespan 的 wait_for_db/seed）；表已由 fixture 建好
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _headers(role: str) -> dict:
    email = {"admin": "admin@boothmap.io", "analyst": "analyst@boothmap.io",
             "viewer": "viewer@boothmap.io"}[role]
    token, _ = create_access_token(email, role)
    return {"Authorization": f"Bearer {token}"}


def _csv() -> bytes:
    return (
        "展商名称,馆号,展位号,优先级,品类\n"
        "甲公司,A1,A1-011,P0,robot\n"
        "乙公司,B2,b2-091,P1,vision\n"
        "坏展位,C1,C1-BAD,P2,software\n"
    ).encode("utf-8")


def test_rbac_denies_non_admin(client):
    # 未登录 401
    assert client.get("/api/imports/batches").status_code == 401
    # analyst / viewer 真实 403
    for role in ("analyst", "viewer"):
        resp = client.get("/api/imports/batches", headers=_headers(role))
        assert resp.status_code == 403, resp.text
        resp = client.post(
            "/api/imports/batches",
            headers=_headers(role),
            json={"batch_code": "X1", "rows": [{"name": "甲公司", "booth_no": "A1-011"}]},
        )
        assert resp.status_code == 403


def test_upload_register_then_publish_and_version_list(client, session_factory):
    resp = client.post(
        "/api/imports/batches/upload",
        headers=_headers("admin"),
        files={"file": ("batch.csv", _csv(), "text/csv")},
        data={"batch_code": "B-HTTP-1", "mode": "supplement"},
    )
    assert resp.status_code == 201, resp.text
    batch = resp.json()
    assert batch["valid_count"] == 2 and batch["quarantine_count"] == 1
    assert batch["status"] == "registered"

    # 隔离行可查且带原因
    staging = client.get(f"/api/imports/batches/{batch['id']}/staging?status=quarantine",
                         headers=_headers("admin")).json()
    assert len(staging["items"]) == 1
    assert staging["items"][0]["reason_codes"] == ["booth_format_invalid"]

    # 发布
    pub = client.post(f"/api/imports/batches/{batch['id']}/publish", headers=_headers("admin"))
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["idempotent"] is False
    assert body["version"]["exhibitor_count"] == 2

    # 重复发布幂等
    pub_again = client.post(f"/api/imports/batches/{batch['id']}/publish", headers=_headers("admin"))
    assert pub_again.status_code == 200
    assert pub_again.json()["idempotent"] is True

    versions = client.get("/api/imports/directory/versions", headers=_headers("admin")).json()
    assert versions["active"] is not None
    assert any(v["is_active"] for v in versions["items"])

    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Exhibitor)) == 2


def test_publish_failure_rolls_back_and_preserves_old_directory(client, session_factory, monkeypatch):
    # 先建一个展商与基线版本作为「旧名录」
    with session_factory() as db:
        exhibitor_service.create_exhibitor(
            db, {"name": "旧展商", "hall": "A1", "booth_no": "A1-099",
                 "category": "robot", "target_industry": "general", "priority": "P1"})
        importer.ensure_baseline(db, created_by="admin")
        db.commit()
        old_total = db.scalar(select(func.count()).select_from(Exhibitor))
        old_active = importer.get_active_version(db)
        old_active_id = old_active.id

    resp = client.post(
        "/api/imports/batches",
        headers=_headers("admin"),
        json={"batch_code": "B-FAIL", "rows": [
            {"name": "新展商甲", "hall": "C1", "booth_no": "C1-011", "category": "software"}]},
    )
    batch_id = resp.json()["id"]

    # 让切换动作在 SAVEPOINT 内抛错
    def boom(*args, **kwargs):
        raise RuntimeError("simulated switch failure")

    monkeypatch.setattr(importer, "apply_publish", boom)
    pub = client.post(f"/api/imports/batches/{batch_id}/publish", headers=_headers("admin"))
    assert pub.status_code == 500

    with session_factory() as db:
        # 名录与展商行未变，旧版本仍 active；批次被标记 failed
        assert db.scalar(select(func.count()).select_from(Exhibitor)) == old_total
        assert importer.get_active_version(db).id == old_active_id
        assert db.get(ImportBatch, batch_id).status == "failed"


def test_rollback_endpoint_switches_active_pointer(client, session_factory):
    # 先有一家展商，并据此冻结基线版本（非空快照）
    with session_factory() as db:
        exhibitor_service.create_exhibitor(
            db, {"name": "基线展商", "hall": "A1", "booth_no": "A1-099",
                 "category": "robot", "target_industry": "general", "priority": "P1"})
        importer.ensure_baseline(db, created_by="admin")
        db.commit()
        baseline_id = importer.get_active_version(db).id

    # 登记并发布一个新批次，产生新版本 v2
    client.post(
        "/api/imports/batches",
        headers=_headers("admin"),
        json={"batch_code": "B-RB", "rows": [
            {"name": "甲公司", "hall": "A1", "booth_no": "A1-011", "category": "robot"}]},
    )
    batches = client.get("/api/imports/batches", headers=_headers("admin")).json()["items"]
    batch_id = batches[0]["id"]
    client.post(f"/api/imports/batches/{batch_id}/publish", headers=_headers("admin"))

    with session_factory() as db:
        new_active = importer.get_active_version(db)
        assert new_active.id != baseline_id

    resp = client.post(f"/api/imports/directory/versions/{baseline_id}/rollback", headers=_headers("admin"))
    assert resp.status_code == 200, resp.text
    with session_factory() as db:
        assert importer.get_active_version(db).id == baseline_id
        # 展商行仍在，只是回滚后不在 active 成员里
        assert db.scalar(select(func.count()).select_from(Exhibitor)) == 2
