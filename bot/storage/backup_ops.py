from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import os
from pathlib import Path
import shutil


@dataclass
class BackupResult:
    success: bool
    backup_path: str | None
    removed_files: list[str]
    error: str | None = None


def create_backup(
    *,
    db_path: str,
    backup_dir: str = "backups",
    retention_days: int = 30,
    now: datetime | None = None,
) -> BackupResult:
    if now is None:
        now = datetime.now(timezone.utc)
    os.makedirs(backup_dir, exist_ok=True)

    if not os.path.exists(db_path):
        return BackupResult(
            success=False,
            backup_path=None,
            removed_files=[],
            error=f"DB file not found: {db_path}",
        )

    stamp = now.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"forwarder-{stamp}.db")
    shutil.copy2(db_path, backup_path)

    removed: list[str] = []
    cutoff = now.timestamp() - (retention_days * 24 * 60 * 60)
    for child in Path(backup_dir).glob("forwarder-*.db"):
        if child.stat().st_mtime < cutoff:
            removed.append(str(child))
            child.unlink(missing_ok=True)

    return BackupResult(
        success=True,
        backup_path=backup_path,
        removed_files=removed,
        error=None,
    )


async def run_backup_scheduler(
    *,
    db_path: str,
    backup_dir: str = "backups",
    retention_days: int = 30,
    interval_seconds: int = 24 * 60 * 60,
) -> None:
    while True:
        try:
            create_backup(
                db_path=db_path,
                backup_dir=backup_dir,
                retention_days=retention_days,
            )
        except Exception:
            # Keep scheduler alive; operator can inspect logs.
            pass
        await asyncio.sleep(interval_seconds)
