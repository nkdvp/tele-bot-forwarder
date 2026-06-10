# Backup and Restore Validation

This guide covers creating, validating, and restoring SQLite backups in DB mode.

## Create a Manual Backup

If admin web is enabled, trigger:

```bash
curl -X POST http://127.0.0.1:8090/api/backup \
  -H "Cookie: admin_session=<session_id>"
```

Or create directly from Python:

```bash
python3 -c "from bot.storage.backup_ops import create_backup; print(create_backup(db_path='data/forwarder.db', backup_dir='backups', retention_days=30))"
```

## Validate a Backup File

```bash
python3 deploy/validate_backup_restore.py --backup backups/forwarder-YYYYMMDD-HHMMSS.db
```

Expected output:

```text
Backup looks valid
```

## Restore Procedure

1. Stop the bot service.
2. Copy backup over active DB:
   ```bash
   cp backups/forwarder-YYYYMMDD-HHMMSS.db data/forwarder.db
   ```
3. Run validation:
   ```bash
   python3 deploy/validate_backup_restore.py --backup data/forwarder.db
   ```
4. Start the bot service.
5. Verify `/health` and forwarding behavior.
