"""批次补录领域模型：导入批次、隔离暂存行、名录版本与版本成员快照。

设计要点（见 services/batch_import/importer.py）：
- ImportBatch  一批官网补发名录的批次头（来源、哈希、状态、核对数量）；
- StagingRow   批次内每一行的清洗结果：valid 入暂存 / quarantine 隔离并带原因；
- DirectoryVersion  名录版本，任一时刻仅一个 active；切换是版本切换而非删表重建；
- DirectoryEntry    版本-展商成员关系（快照），回滚只切版本指针，不删除任何展商行，
                    因此「切换失败恢复旧版」天然不丢数据。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow

# 批次状态
BATCH_REGISTERED = "registered"
BATCH_PUBLISHED = "published"
BATCH_FAILED = "failed"
BATCH_STATUS = (BATCH_REGISTERED, BATCH_PUBLISHED, BATCH_FAILED)

# 暂存行状态
STAGING_VALID = "valid"
STAGING_QUARANTINE = "quarantine"

# 名录版本状态
VERSION_ACTIVE = "active"
VERSION_RETIRED = "retired"
VERSION_ROLLED_BACK = "rolled_back"

# 导入模式：supplement=批次补录（默认，保留旧名录）；snapshot=整份快照（以本批为准）
MODE_SUPPLEMENT = "supplement"
MODE_SNAPSHOT = "snapshot"
IMPORT_MODES = (MODE_SUPPLEMENT, MODE_SNAPSHOT)


class ImportBatch(Base):
    """一次批次补录：来源文件、内容哈希、校验/发布状态与核对口径数量。"""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16), default=MODE_SUPPLEMENT)
    status: Mapped[str] = mapped_column(String(16), default=BATCH_REGISTERED, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    quarantine_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    reconciliation: Mapped[dict] = mapped_column(JSON, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), default="system")
    published_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StagingRow(Base):
    """批次内一行：保留原始载荷与规范化结果；坏行进 quarantine 并写明原因码。"""

    __tablename__ = "import_staging_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_no", name="uq_staging_batch_row"),
        Index("ix_staging_batch_status", "batch_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=STAGING_VALID, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    reason_detail: Mapped[str] = mapped_column(String(500), default="")
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    match_exhibitor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DirectoryVersion(Base):
    """名录版本：整批校验通过后一次性切换；回滚即把 active 指针切回旧版本。"""

    __tablename__ = "directory_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_no: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(16), default=VERSION_ACTIVE, index=True)
    source_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    exhibitor_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(160), default="system")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DirectoryEntry(Base):
    """版本成员快照：(版本, 展商) 多对多。展商行永不因切换/回滚被删除。"""

    __tablename__ = "directory_entries"
    __table_args__ = (
        UniqueConstraint("version_id", "exhibitor_id", name="uq_directory_entry"),
        Index("ix_directory_entry_exhibitor", "exhibitor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("directory_versions.id", ondelete="CASCADE"), index=True)
    exhibitor_id: Mapped[int] = mapped_column(ForeignKey("exhibitors.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
