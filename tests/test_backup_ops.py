from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3

from bot.storage.backup_ops import create_backup
from bot.storage.sqlite_db import initialize_database


def test_create_backup_creates_file_and_prunes_old(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    backup_dir = str(tmp_path / "backups")
    initialize_database(db_path)

    old_file = Path(backup_dir) / "forwarder-old.db"
    os.makedirs(backup_dir, exist_ok=True)
    old_file.write_text("old")
    old_time = datetime.now(timezone.utc) - timedelta(days=40)
    os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))

    result = create_backup(
        db_path=db_path,
        backup_dir=backup_dir,
        retention_days=30,
    )

    assert result.success is True
    assert result.backup_path is not None
    assert Path(result.backup_path).exists()
    assert str(old_file) in result.removed_files
    assert not old_file.exists()


def test_create_backup_returns_error_for_missing_db(tmp_path):
    result = create_backup(
        db_path=str(tmp_path / "missing.db"),
        backup_dir=str(tmp_path / "backups"),
        retention_days=30,
    )
    assert result.success is False
    assert result.backup_path is None
    assert result.error is not None
