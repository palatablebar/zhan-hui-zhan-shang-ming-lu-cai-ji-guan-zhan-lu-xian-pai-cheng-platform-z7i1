"""批次补录核心服务：登记（清洗/隔离/查重）→ 整批校验 → 一次性版本切换 → 可回滚。

事务与切换口径
--------------
1. ``register_batch`` 只写 ``import_batches`` / ``import_staging_rows`` 两张暂存表，
   绝不触碰正式 ``exhibitors``，因此坏行不会污染现网名录。
2. ``publish_batch`` 在**单个事务**内：合并好行入册 → 生成新版本成员快照 → 翻转
   ``active`` 版本指针。任一步抛错则整体回滚，旧版本保持 active，展商行不删除、
   不覆盖，满足「切换失败恢复旧版且不丢数据」。
3. 名录对平面图/两日排程的可见性以 ``DirectoryEntry``（当前 active 版本成员）为准，
   切换是指针翻转，回滚同样只翻指针，历史版本与展商行全部保留。
4. 批次以 ``batch_code`` 为幂等键、以来源内容 ``sha256`` 防重放：重复登记/发布直接
   返回既有结果，不新增也不覆盖人工修改（合并阶段对已存在展商零写入）。
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.exhibitor import Exhibitor
from src.models.import_batch import (
    BATCH_FAILED,
    BATCH_PUBLISHED,
    BATCH_REGISTERED,
    DirectoryEntry,
    DirectoryVersion,
    ImportBatch,
    MODE_SNAPSHOT,
    MODE_SUPPLEMENT,
    STAGING_QUARANTINE,
    STAGING_VALID,
    VERSION_ACTIVE,
    VERSION_RETIRED,
    VERSION_ROLLED_BACK,
    StagingRow,
)
from src.services import audit_service, exhibitor_service
from src.services.batch_import.normalizer import (
    REASON_DUPLICATE_BATCH,
    REASON_LABELS,
    normalize_row,
    row_fingerprint,
)
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


# --------------------------------------------------------------------------- #
# 版本辅助
# --------------------------------------------------------------------------- #
def get_active_version(db: Session) -> DirectoryVersion | None:
    return db.scalar(select(DirectoryVersion).where(DirectoryVersion.status == VERSION_ACTIVE).order_by(DirectoryVersion.version_no.desc()))


def get_version(db: Session, version_id: int) -> DirectoryVersion:
    version = db.get(DirectoryVersion, version_id)
    if version is None:
        raise AppError("NOT_FOUND", 404, {"entity": "directory_version", "id": version_id})
    return version


def active_exhibitor_ids(db: Session) -> set[int]:
    """当前 active 名录版本的成员 id 集合。

    尚无任何版本（例如全新库还没发布过批次）时返回空集合，由调用方决定回退口径；
    为不破坏既有 seed 演示，读取侧在空集合时回退为「全部展商」。
    """
    version = get_active_version(db)
    if version is None:
        return set()
    return set(db.scalars(select(DirectoryEntry.exhibitor_id).where(DirectoryEntry.version_id == version.id)).all())


def active_version_scoped(db: Session) -> tuple[DirectoryVersion | None, set[int] | None]:
    """返回 (active 版本, 成员 id 集合)；无版本时成员集合为 None 表示「不裁剪」。"""
    version = get_active_version(db)
    if version is None:
        return None, None
    return version, active_exhibitor_ids(db)


def _next_version_no(db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.max(DirectoryVersion.version_no), 0))) or 0) + 1


def ensure_baseline(db: Session, *, created_by: str = "system") -> DirectoryVersion:
    """确保存在一个基线版本（纳入当前全部展商）。

    首次发布前若名录已有数据（例如 seed 的 186 家），先冻结成 v1 基线，
    之后的批次切换才有「旧版名录」可回滚。幂等：已有任意版本则直接返回 active。
    """
    existing = get_active_version(db)
    if existing is not None:
        return existing
    version = DirectoryVersion(
        version_no=_next_version_no(db),
        label="基线名录（首次批次补录前快照）",
        status=VERSION_ACTIVE,
        source_batch_id=None,
        created_by=created_by,
        published_at=utcnow(),
    )
    db.add(version)
    db.flush()
    exhibitor_ids = db.scalars(select(Exhibitor.id).order_by(Exhibitor.id)).all()
    db.add_all([DirectoryEntry(version_id=version.id, exhibitor_id=eid) for eid in exhibitor_ids])
    version.exhibitor_count = len(exhibitor_ids)
    db.flush()
    return version


# --------------------------------------------------------------------------- #
# 登记：清洗 / 隔离 / 批内查重 / 现册匹配
# --------------------------------------------------------------------------- #
def register_batch(
    db: Session,
    rows: Sequence[dict],
    *,
    source_name: str,
    source_sha256: str,
    batch_code: str,
    mode: str = MODE_SUPPLEMENT,
    created_by: str = "system",
) -> ImportBatch:
    """把一批原始行清洗进暂存区。好行 valid，坏行 quarantine 并写原因码。

    幂等：相同 ``batch_code`` 重复登记直接返回既有批次，不产生任何新写入。
    """
    if mode not in (MODE_SUPPLEMENT, MODE_SNAPSHOT):
        raise AppError("VALIDATION", 422, {"field": "mode", "message": "mode 仅支持 supplement / snapshot"})

    existing = db.scalar(select(ImportBatch).where(ImportBatch.batch_code == batch_code))
    if existing is not None:
        return existing

    batch = ImportBatch(
        batch_code=batch_code,
        source_name=source_name or "",
        source_sha256=source_sha256,
        mode=mode,
        status=BATCH_REGISTERED,
        created_by=created_by,
        total_rows=len(rows),
    )
    db.add(batch)
    db.flush()

    # 现册 (hall, booth_no) -> exhibitor，用于合并/人工修改识别
    registry = {
        (row.hall, row.booth_no): row
        for row in db.scalars(select(Exhibitor)).all()
    }
    seen_booth: set[tuple[str, str]] = set()
    valid_count = 0
    quarantine_count = 0

    for index, raw in enumerate(rows, start=1):
        normalized = normalize_row(index, raw)
        reason_codes = list(normalized.reason_codes)

        # 批内同馆同展位查重：首个保留，后续标记重复（即便其它字段合法也隔离）
        match_exhibitor_id = None
        if normalized.ok:
            key = (normalized.hall, normalized.booth_no)
            if key in seen_booth:
                reason_codes.append(REASON_DUPLICATE_BATCH)
            else:
                seen_booth.add(key)
                matched = registry.get(key)
                if matched is not None:
                    match_exhibitor_id = matched.id

        if reason_codes:
            quarantine_count += 1
            db.add(
                StagingRow(
                    batch_id=batch.id,
                    row_no=index,
                    status=STAGING_QUARANTINE,
                    raw_payload=_jsonable(raw),
                    normalized=_jsonable(normalized.cleaned),
                    reason_codes=reason_codes,
                    reason_detail="；".join(REASON_LABELS.get(code, code) for code in reason_codes),
                    fingerprint=None,
                    match_exhibitor_id=match_exhibitor_id,
                )
            )
            continue

        valid_count += 1
        cleaned = dict(normalized.cleaned)
        fingerprint = row_fingerprint(cleaned)
        db.add(
            StagingRow(
                batch_id=batch.id,
                row_no=index,
                status=STAGING_VALID,
                raw_payload=_jsonable(raw),
                normalized=_jsonable(cleaned),  # 落库副本转 JSON 安全；内存 cleaned 仍保留 datetime
                reason_codes=[],
                reason_detail="",
                fingerprint=fingerprint,
                match_exhibitor_id=match_exhibitor_id,
            )
        )

    batch.valid_count = valid_count
    batch.quarantine_count = quarantine_count
    db.flush()  # autoflush=False：先落暂存行，核对查询才能读到本批数据
    batch.reconciliation = build_reconciliation(db, batch)
    db.flush()
    return batch


def build_reconciliation(db: Session, batch: ImportBatch) -> dict:
    """核对来源 / 入册 / 隔离 / 合并数量，并校验恒等关系。"""
    valid_rows = db.scalars(
        select(StagingRow).where(StagingRow.batch_id == batch.id, StagingRow.status == STAGING_VALID)
    ).all()
    quarantine_rows = db.scalars(
        select(StagingRow).where(StagingRow.batch_id == batch.id, StagingRow.status == STAGING_QUARANTINE)
    ).all()

    registry = {(row.hall, row.booth_no): row for row in db.scalars(select(Exhibitor)).all()}
    merged = 0
    new = 0
    manual_edits = 0
    for staging in valid_rows:
        key = (staging.normalized["hall"], staging.normalized["booth_no"])
        exhibitor = registry.get(key)
        if exhibitor is None:
            new += 1
            continue
        merged += 1
        if _differs_from_source(exhibitor, staging.normalized):
            manual_edits += 1

    checks = {
        "total_equals_valid_plus_quarantine": batch.total_rows == len(valid_rows) + len(quarantine_rows),
        "no_valid_duplicate_booth": _no_valid_duplicate(valid_rows),
        "counts_non_negative": batch.total_rows >= 0 and len(valid_rows) >= 0 and len(quarantine_rows) >= 0,
    }
    return {
        "source_rows": batch.total_rows,
        "valid_rows": len(valid_rows),
        "quarantine_rows": len(quarantine_rows),
        "would_insert": new,
        "would_merge": merged,
        "manual_edited_existing": manual_edits,
        "quarantine_reason_breakdown": _reason_breakdown(quarantine_rows),
        "checks": checks,
        "reconciled": all(checks.values()),
    }


def _no_valid_duplicate(valid_rows: Sequence[StagingRow]) -> bool:
    keys = [(row.normalized["hall"], row.normalized["booth_no"]) for row in valid_rows]
    return len(keys) == len(set(keys))


def _reason_breakdown(quarantine_rows: Sequence[StagingRow]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for row in quarantine_rows:
        for code in row.reason_codes or []:
            breakdown[code] = breakdown.get(code, 0) + 1
    return dict(sorted(breakdown.items()))


def _differs_from_source(exhibitor: Exhibitor, cleaned: dict) -> bool:
    """现册行与本批来源是否存在人工修改：只比较来源可携带的字段。

    展商行在合并阶段不会被覆盖，这里仅用于报告「哪些已被现场同事改过」。
    """
    comparable = (
        "name",
        "category",
        "target_industry",
        "contact_name",
        "contact_title",
        "contact_phone",
        "priority",
        "dwell_min",
    )
    for field in comparable:
        if str(getattr(exhibitor, field, "")) != str(cleaned.get(field, "")):
            return True
    return False


# --------------------------------------------------------------------------- #
# 发布：整批校验通过后，单事务一次性切换新名录
# --------------------------------------------------------------------------- #
def precheck_publish(db: Session, batch_id: int) -> tuple[ImportBatch, dict]:
    """发布前整批校验。失败时把批次标记为 FAILED（该标记可独立提交，不参与切换事务）。

    返回 (batch, reconciliation)。隔离行存在是允许的（它们本就不进名录）；
    只有数量恒等式被破坏等结构性问题才判定校验不通过。
    """
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise AppError("NOT_FOUND", 404, {"entity": "import_batch", "id": batch_id})
    if batch.status == BATCH_PUBLISHED and batch.published_version_id:
        return batch, build_reconciliation(db, batch)
    if batch.status == BATCH_FAILED:
        raise AppError("CONFLICT", 409, {"message": "该批次曾发布失败，请修正后重新登记新批次"})

    reconciliation = build_reconciliation(db, batch)
    if not reconciliation["reconciled"]:
        batch.status = BATCH_FAILED
        batch.error_text = "整批校验未通过，拒绝切换名录"
        raise AppError("VALIDATION", 422, {"message": batch.error_text, "reconciliation": reconciliation})
    return batch, reconciliation


def apply_publish(
    db: Session,
    batch: ImportBatch,
    reconciliation: dict,
    *,
    created_by: str,
    principal: dict | None = None,
    ip: str | None = None,
) -> DirectoryVersion:
    """实际切换：合并好行 → 新版本快照 → 翻转 active 指针。

    本函数不捕获异常，交由外层事务/SAVEPOINT 整体回滚；因此任何失败都不会留下
    半成品名录，旧版本保持 active，展商行零删除、已有人工修改零覆盖。
    """
    baseline = ensure_baseline(db, created_by=created_by)
    previous_active = get_active_version(db)

    valid_rows = db.scalars(
        select(StagingRow)
        .where(StagingRow.batch_id == batch.id, StagingRow.status == STAGING_VALID)
        .order_by(StagingRow.row_no)
    ).all()

    inserted = 0
    merged = 0
    for staging in valid_rows:
        cleaned = staging.normalized
        exhibitor = db.scalar(
            select(Exhibitor).where(
                Exhibitor.hall == cleaned["hall"], Exhibitor.booth_no == cleaned["booth_no"]
            )
        )
        if exhibitor is None:
            # 仅新增全新展位；已存在展商零写入，人工修改原样保留
            payload = _exhibitor_payload(cleaned)
            exhibitor = exhibitor_service.create_exhibitor(db, payload)
            inserted += 1
        else:
            merged += 1
        staging.match_exhibitor_id = exhibitor.id

    # 组装新版本成员快照
    if batch.mode == MODE_SNAPSHOT:
        member_ids = sorted({staging.match_exhibitor_id for staging in valid_rows if staging.match_exhibitor_id})
    else:
        member_ids = sorted(
            set(active_exhibitor_ids(db))
            | {staging.match_exhibitor_id for staging in valid_rows if staging.match_exhibitor_id}
        )

    version = DirectoryVersion(
        version_no=_next_version_no(db),
        label=f"批次 {batch.batch_code} 发布（{batch.mode}）",
        status=VERSION_ACTIVE,
        source_batch_id=batch.id,
        created_by=created_by,
        exhibitor_count=len(member_ids),
        published_at=utcnow(),
    )
    db.add(version)
    db.flush()
    db.add_all([DirectoryEntry(version_id=version.id, exhibitor_id=eid) for eid in member_ids])

    # 翻转 active 指针：旧版本退休（保留快照供回滚），同事务保证只有一个 active
    if previous_active is not None and previous_active.id != version.id:
        previous_active.status = VERSION_RETIRED

    batch.status = BATCH_PUBLISHED
    batch.published_at = utcnow()
    batch.published_version_id = version.id
    batch.inserted_count = inserted
    batch.merged_count = merged
    batch.skipped_count = merged  # 合并行均跳过写入（不覆盖人工修改）
    batch.reconciliation = reconciliation | {
        "published_version_id": version.id,
        "previous_version_id": previous_active.id if previous_active else baseline.id,
        "published_member_count": len(member_ids),
        "inserted": inserted,
        "merged": merged,
        "skipped": merged,
    }

    actor = principal or {"email": created_by, "role": "admin"}
    audit_service.record(
        db,
        actor_email=actor.get("email", created_by),
        actor_role=actor.get("role", "admin"),
        action="directory.publish",
        entity="directory_version",
        entity_id=version.id,
        detail={
            "batch_code": batch.batch_code,
            "mode": batch.mode,
            "source_rows": batch.total_rows,
            "inserted": inserted,
            "merged": merged,
            "quarantine": batch.quarantine_count,
            "version_no": version.version_no,
        },
        ip=ip,
    )
    db.flush()
    return version


def publish_batch(db: Session, batch_id: int, *, created_by: str, principal: dict | None = None, ip: str | None = None) -> DirectoryVersion:
    """整批校验通过后，单事务一次性切换新名录（CLI 等单事务入口使用）。"""
    batch, reconciliation = precheck_publish(db, batch_id)
    if batch.status == BATCH_PUBLISHED and batch.published_version_id:
        return get_version(db, batch.published_version_id)
    return apply_publish(db, batch, reconciliation, created_by=created_by, principal=principal, ip=ip)


def rollback_to_version(db: Session, version_id: int, *, created_by: str, principal: dict | None = None, ip: str | None = None) -> DirectoryVersion:
    """把名录切回指定历史版本：仅翻转版本指针与成员可见性，不删除任何展商行。"""
    target = get_version(db, version_id)
    current = get_active_version(db)
    if current is not None and current.id == target.id:
        return target

    member_count = db.scalar(
        select(func.count()).select_from(DirectoryEntry).where(DirectoryEntry.version_id == target.id)
    ) or 0
    if member_count == 0:
        raise AppError("CONFLICT", 409, {"message": "目标版本为空快照，拒绝回滚"})

    if current is not None:
        current.status = VERSION_ROLLED_BACK
    target.status = VERSION_ACTIVE
    target.published_at = utcnow()

    actor = principal or {"email": created_by, "role": "admin"}
    audit_service.record(
        db,
        actor_email=actor.get("email", created_by),
        actor_role=actor.get("role", "admin"),
        action="directory.rollback",
        entity="directory_version",
        entity_id=target.id,
        detail={"from_version_id": current.id if current else None, "to_version_id": target.id, "member_count": member_count},
        ip=ip,
    )
    db.flush()
    return target


# --------------------------------------------------------------------------- #
# 查询序列化
# --------------------------------------------------------------------------- #
def serialize_batch(db: Session, batch: ImportBatch) -> dict:
    return {
        "id": batch.id,
        "batch_code": batch.batch_code,
        "source_name": batch.source_name,
        "source_sha256": batch.source_sha256,
        "mode": batch.mode,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "valid_count": batch.valid_count,
        "quarantine_count": batch.quarantine_count,
        "inserted_count": batch.inserted_count,
        "merged_count": batch.merged_count,
        "skipped_count": batch.skipped_count,
        "reconciliation": batch.reconciliation or {},
        "error_text": batch.error_text,
        "created_by": batch.created_by,
        "published_version_id": batch.published_version_id,
        "created_at": iso_utc(batch.created_at),
        "published_at": iso_utc(batch.published_at),
    }


def list_staging(db: Session, batch_id: int, status: str | None = None) -> list[dict]:
    stmt = select(StagingRow).where(StagingRow.batch_id == batch_id)
    if status:
        stmt = stmt.where(StagingRow.status == status)
    rows = db.scalars(stmt.order_by(StagingRow.row_no)).all()
    return [
        {
            "row_no": row.row_no,
            "status": row.status,
            "raw": row.raw_payload,
            "normalized": row.normalized,
            "reason_codes": row.reason_codes or [],
            "reason_labels": [REASON_LABELS.get(code, code) for code in (row.reason_codes or [])],
            "reason_detail": row.reason_detail,
            "fingerprint": row.fingerprint,
            "match_exhibitor_id": row.match_exhibitor_id,
        }
        for row in rows
    ]


def list_versions(db: Session) -> list[dict]:
    rows = db.scalars(select(DirectoryVersion).order_by(DirectoryVersion.version_no.desc())).all()
    active = get_active_version(db)
    return [
        {
            "id": row.id,
            "version_no": row.version_no,
            "label": row.label,
            "status": row.status,
            "is_active": active is not None and active.id == row.id,
            "source_batch_id": row.source_batch_id,
            "exhibitor_count": row.exhibitor_count,
            "created_by": row.created_by,
            "created_at": iso_utc(row.created_at),
            "published_at": iso_utc(row.published_at),
        }
        for row in rows
    ]


def _exhibitor_payload(cleaned: dict) -> dict:
    payload = dict(cleaned)
    appointment = payload.pop("appointment_at", None)
    payload.pop("appointment_window_min", None)
    if appointment is not None:
        if isinstance(appointment, str):
            # 暂存 JSON 列读回时 datetime 是 ISO 字符串，这里还原为 datetime 供硬窗校验
            from datetime import datetime

            appointment = datetime.fromisoformat(appointment)
        payload["appointment_at"] = appointment
        payload["appointment_window_min"] = cleaned.get("appointment_window_min", 30)
    return payload


def _jsonable(value):
    """递归把 JSON 列载荷里的 datetime/date 转成 ISO 字符串，保证可被数据库 JSON 序列化。

    CSV 路径给的是字符串，但 JSON API 可能直接给 datetime；暂存的 normalized/raw
    都走这里统一兜底，避免 MySQL/SQLite 写入 JSON 列时类型报错。
    """
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
