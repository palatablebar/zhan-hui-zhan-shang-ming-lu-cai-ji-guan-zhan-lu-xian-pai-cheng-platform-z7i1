"""批次补录端到端单测：SQLite 内存库验证隔离、幂等、人工修改保留、版本切换与回滚。

不依赖 MySQL/Redis：所有服务函数都接收 Session，这里自建 in-memory 引擎注入即可。
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base
from src.models.exhibitor import Exhibitor
from src.models.import_batch import (
    BATCH_PUBLISHED,
    BATCH_REGISTERED,
    DirectoryEntry,
    DirectoryVersion,
    ImportBatch,
    STAGING_QUARANTINE,
    VERSION_ACTIVE,
    VERSION_RETIRED,
    VERSION_ROLLED_BACK,
    StagingRow,
)
from src.services.batch_import import importer
from src.services.batch_import.normalizer import REASON_DUPLICATE_BATCH
from src.utils.errors import AppError

ADMIN = {"email": "admin@boothmap.io", "role": "admin"}


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    session = maker()
    yield session
    session.close()
    engine.dispose()


def _good_row(name: str, booth: str, **over) -> dict:
    row = {"name": name, "hall": booth.split("-")[0], "booth_no": booth, "priority": "P1",
           "category": "robot", "target_industry": "general"}
    row.update(over)
    return row


def _exhibitor_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Exhibitor)) or 0


# --------------------------------------------------------------------------- #
# 登记：好行入暂存、坏行隔离、批内查重、暂不写正式名录
# --------------------------------------------------------------------------- #
def test_register_splits_good_and_quarantine_and_does_not_touch_directory(db):
    rows = [
        _good_row("甲公司", "A1-011"),
        _good_row("乙公司", "A1-012", booth_no="a1馆12号"),           # 异写法，规范化后同 A1-012
        {"name": "坏展位", "booth_no": "BAD-FORMAT", "category": "robot"},
        {"name": "坏优先级", "booth_no": "A1-013", "priority": "P9"},
        _good_row("重复甲", "A1-011"),                                 # 与首行同馆同展位
    ]
    batch = importer.register_batch(db, rows, source_name="b.csv", source_sha256="h1",
                                    batch_code="B-001", created_by=ADMIN["email"])

    assert batch.total_rows == 5
    assert batch.valid_count == 2            # 甲、乙（乙的中文写法被规范化）
    assert batch.quarantine_count == 3
    assert _exhibitor_count(db) == 0         # 登记阶段绝不写正式名录

    staging = db.scalars(select(StagingRow).where(StagingRow.batch_id == batch.id)).all()
    quarantined = [s for s in staging if s.status == STAGING_QUARANTINE]
    reasons = {code for s in quarantined for code in s.reason_codes}
    assert REASON_DUPLICATE_BATCH in reasons
    assert all(s.reason_detail for s in quarantined)  # 每条坏行都有可读原因

    recon = batch.reconciliation
    assert recon["source_rows"] == recon["valid_rows"] + recon["quarantine_rows"]
    assert recon["reconciled"] is True


def test_register_is_idempotent_by_batch_code(db):
    rows = [_good_row("甲公司", "A1-011")]
    first = importer.register_batch(db, rows, source_name="b.csv", source_sha256="h",
                                    batch_code="B-DUP", created_by=ADMIN["email"])
    # 同 code 再登记（即便内容有变化）返回同一批次，不新增暂存行
    again = importer.register_batch(db, [_good_row("其它", "A2-021")], source_name="b.csv",
                                    source_sha256="h2", batch_code="B-DUP", created_by=ADMIN["email"])
    assert again.id == first.id
    assert db.scalar(select(func.count()).select_from(StagingRow).where(StagingRow.batch_id == first.id)) == 1


# --------------------------------------------------------------------------- #
# 发布：整批校验 → 单事务切换；数量核对
# --------------------------------------------------------------------------- #
def test_publish_creates_version_and_scopes_floorplan_and_schedule(db):
    # 既有 2 家展商模拟现网名录
    for name, booth in [("旧甲", "A1-011"), ("旧乙", "A1-012")]:
        importer.exhibitor_service.create_exhibitor(db, _good_row(name, booth))
    db.flush()
    assert _exhibitor_count(db) == 2

    batch = importer.register_batch(
        db,
        [_good_row("旧甲", "A1-011"), _good_row("新增丙", "C1-031"),
         {"name": "坏", "booth_no": "XX", "category": "robot"}],
        source_name="b.csv", source_sha256="h", batch_code="B-002", created_by=ADMIN["email"],
    )
    assert batch.valid_count == 2 and batch.quarantine_count == 1

    version = importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()

    # 数量核对：来源=入册好行+隔离；新增 1、合并 1（旧甲已存在）
    assert batch.status == BATCH_PUBLISHED
    assert batch.inserted_count == 1
    assert batch.merged_count == 1
    assert batch.skipped_count == 1
    assert _exhibitor_count(db) == 3                 # 仅新增「新增丙」，坏行未入册

    # 版本：基线 v1 + 发布版 v2，且只有一个 active
    versions = db.scalars(select(DirectoryVersion).order_by(DirectoryVersion.version_no)).all()
    assert [v.version_no for v in versions] == [1, 2]
    actives = [v for v in versions if v.status == VERSION_ACTIVE]
    assert len(actives) == 1 and actives[0].id == version.id
    assert versions[0].status == VERSION_RETIRED

    # 平面图/排程读取口径只看 active 版本成员（基线 2 + 新增 1 = 3）
    members = importer.active_exhibitor_ids(db)
    assert members == set(db.scalars(select(Exhibitor.id)).all())
    assert version.exhibitor_count == 3


def test_publish_is_idempotent_and_never_overwrites_manual_edits(db):
    # 现场同事把「旧甲」优先级人工改成 P0
    created = importer.exhibitor_service.create_exhibitor(db, _good_row("旧甲", "A1-011", priority="P2"))
    db.flush()
    exhibitor_id = created.id
    created.priority = "P0"
    db.flush()

    # 官网补发同展位仍是 P2，且改名/改电话
    batch = importer.register_batch(
        db,
        [_good_row("旧甲-官网名", "A1-011", priority="P2", contact_name="新联系人", contact_phone="13900000000")],
        source_name="b.csv", source_sha256="h", batch_code="B-003", created_by=ADMIN["email"],
    )
    recon = importer.build_reconciliation(db, batch)
    assert recon["would_merge"] == 1
    assert recon["manual_edited_existing"] == 1   # 识别人工修改

    importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()
    after = db.get(Exhibitor, exhibitor_id)
    assert after.priority == "P0"                  # 人工 P0 未被官网 P2 覆盖
    assert after.name == "旧甲"                    # 名称等字段也零覆盖
    assert after.contact_phone == ""
    assert batch.inserted_count == 0 and batch.merged_count == 1

    # 重复发布：幂等 no-op，不新增版本、不新增展商
    versions_before = db.scalar(select(func.count()).select_from(DirectoryVersion))
    again = importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()
    assert again.id == batch.published_version_id
    assert db.scalar(select(func.count()).select_from(DirectoryVersion)) == versions_before
    assert _exhibitor_count(db) == 1


# --------------------------------------------------------------------------- #
# 回滚：切回旧版，成员可见性恢复，展商行不删除
# --------------------------------------------------------------------------- #
def test_rollback_restores_previous_version_without_deleting_rows(db):
    importer.exhibitor_service.create_exhibitor(db, _good_row("旧甲", "A1-011"))
    db.flush()
    batch = importer.register_batch(
        db, [_good_row("新增丙", "C1-031")], source_name="b.csv", source_sha256="h",
        batch_code="B-004", created_by=ADMIN["email"],
    )
    v2 = importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()
    v1 = db.scalar(select(DirectoryVersion).where(DirectoryVersion.version_no == 1))
    assert importer.active_exhibitor_ids(db) == set(db.scalars(select(Exhibitor.id)).all())  # 2 家

    importer.rollback_to_version(db, v1.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()

    current = importer.get_active_version(db)
    assert current.id == v1.id
    assert db.get(DirectoryVersion, v2.id).status == VERSION_ROLLED_BACK
    # 成员可见性回到基线（仅旧甲），但「新增丙」展商行仍在，未被删除
    baseline_members = set(
        db.scalars(select(DirectoryEntry.exhibitor_id).where(DirectoryEntry.version_id == v1.id)).all()
    )
    assert importer.active_exhibitor_ids(db) == baseline_members
    assert _exhibitor_count(db) == 2


def test_rollback_rejects_empty_snapshot(db):
    # 手工构造一个没有成员的版本，回滚应被拒绝
    empty = DirectoryVersion(version_no=99, label="空", status=VERSION_RETIRED, exhibitor_count=0)
    db.add(empty)
    db.flush()
    with pytest.raises(AppError):
        importer.rollback_to_version(db, empty.id, created_by=ADMIN["email"], principal=ADMIN)


# --------------------------------------------------------------------------- #
# 发布失败：旧版本保持 active、无数据丢失、批次留痕
# --------------------------------------------------------------------------- #
def test_failed_apply_keeps_old_version_and_marks_batch(db, monkeypatch):
    importer.exhibitor_service.create_exhibitor(db, _good_row("旧甲", "A1-011"))
    db.flush()
    batch = importer.register_batch(
        db, [_good_row("新增丙", "C1-031")], source_name="b.csv", source_sha256="h",
        batch_code="B-005", created_by=ADMIN["email"],
    )
    before_count = _exhibitor_count(db)
    batch_id, recon = importer.precheck_publish(db, batch.id)

    # 模拟切换过程中底层异常（例如约束冲突）
    def boom(*args, **kwargs):
        raise RuntimeError("simulated switch failure")

    monkeypatch.setattr(importer, "ensure_baseline", boom)
    savepoint = db.begin_nested()
    with pytest.raises(RuntimeError):
        importer.apply_publish(db, batch_id, recon, created_by=ADMIN["email"], principal=ADMIN)
    savepoint.rollback()

    # 旧名录（基线尚未来得及建，则仍无版本）与展商行完好
    assert _exhibitor_count(db) == before_count
    assert db.get(ImportBatch, batch.id).status == BATCH_REGISTERED  # 回滚后批次未被误标成功


def test_snapshot_mode_version_contains_only_batch_members(db):
    importer.exhibitor_service.create_exhibitor(db, _good_row("旧甲", "A1-011"))
    importer.exhibitor_service.create_exhibitor(db, _good_row("旧乙", "A1-012"))
    db.flush()
    batch = importer.register_batch(
        db, [_good_row("新丙", "C1-031")], source_name="b.csv", source_sha256="h",
        batch_code="B-006", mode="snapshot", created_by=ADMIN["email"],
    )
    version = importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.flush()
    # snapshot 模式新版本只含本批好行成员（新丙），旧展商行仍保留在库与基线快照中
    assert version.exhibitor_count == 1
    assert importer.active_exhibitor_ids(db) == {db.scalar(
        select(Exhibitor.id).where(Exhibitor.booth_no == "C1-031"))}
    assert _exhibitor_count(db) == 3


def test_appointment_roundtrip_across_sessions(db):
    """暂存 JSON 列里的预约时间落库后是字符串，发布时必须能还原为 datetime 建展商。"""
    from datetime import datetime

    rows = [_good_row("甲公司", "A1-011", appointment_at="2026-11-18 10:30")]
    batch = importer.register_batch(db, rows, source_name="b.csv", source_sha256="h",
                                    batch_code="B-RT", created_by=ADMIN["email"])
    db.commit()
    db.expire_all()  # 强制后续从数据库重新读，模拟 CLI/API 的跨会话场景

    version = importer.publish_batch(db, batch.id, created_by=ADMIN["email"], principal=ADMIN)
    db.commit()
    exhibitor = db.scalar(select(Exhibitor).where(Exhibitor.booth_no == "A1-011"))
    assert exhibitor is not None
    assert isinstance(exhibitor.appointment_at, datetime)
    assert exhibitor.appointment_day == 1
    assert exhibitor.appointment_start_min == 630
    assert version.exhibitor_count == 1


def test_reconciliation_identity_and_breakdown(db):
    rows = [
        _good_row("甲方公司", "A1-011"),
        {"name": "坏1", "booth_no": "BAD", "category": "robot"},
        {"name": "坏2", "booth_no": "A1-012", "priority": "P9"},
    ]
    batch = importer.register_batch(db, rows, source_name="b.csv", source_sha256="h",
                                    batch_code="B-007", created_by=ADMIN["email"])
    recon = batch.reconciliation
    assert recon["source_rows"] == 3
    assert recon["valid_rows"] == 1 and recon["quarantine_rows"] == 2
    assert recon["checks"]["total_equals_valid_plus_quarantine"] is True
    assert isinstance(recon["quarantine_reason_breakdown"], dict) and recon["quarantine_reason_breakdown"]
