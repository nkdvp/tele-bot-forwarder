# DB Migration Rollback Runbook

This runbook describes how to switch between file-backed mode and DB-backed mode safely.

## Runtime Mode Flags

- `USE_DB_CONFIG=true`: bot uses SQLite-backed reply links and config store wiring.
- `USE_DB_CONFIG=false` (default): bot uses file-backed `data/reply_map.json` and existing YAML config flow.
- `DB_PATH`: optional override for DB file path (default `data/forwarder.db`).

## Safe Cutover (File -> DB)

1. Create or refresh DB content:
   ```bash
   python3 -m bot.storage.db_migration \
     --config config.yaml \
     --reply-map data/reply_map.json \
     --db data/forwarder.db \
     --dry-run
   ```
2. Verify the JSON report has `"success": true`.
3. Run migration without `--dry-run`.
4. Set `USE_DB_CONFIG=true` in runtime environment.
5. Restart service and validate forwarding/reply threading.

## Rollback (DB -> File)

1. Set `USE_DB_CONFIG=false`.
2. Restart service.
3. Confirm bot uses file-backed reply map behavior.
4. If needed, inspect DB migration report/errors before retrying cutover.

## Notes

- Rollback does not require deleting the DB file.
- Keep `config.yaml` and `data/reply_map.json` available until rollout is stable.
- Treat migration as repeatable: rerun with `--dry-run` before each production cutover.
