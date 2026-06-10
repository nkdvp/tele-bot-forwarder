import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.storage.auth_store import AuthStore
from bot.storage.config_store import PairFilters, PairRecord, SQLiteConfigStore
from bot.storage.sqlite_db import initialize_database
from bot.web.admin_app import create_admin_app


async def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    config_store = SQLiteConfigStore(db_path)
    auth_store = AuthStore(db_path)
    auth_store.ensure_admin_user("admin", "secret")
    app = create_admin_app(
        db_path=db_path,
        config_store=config_store,
        auth_store=auth_store,
        backup_dir=str(tmp_path / "backups"),
        backup_retention_days=30,
        stats_path=str(tmp_path / "stats.json"),
    )
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client, db_path


async def _login(client: TestClient) -> None:
    resp = await client.post(
        "/api/login",
        json={"username": "admin", "password": "secret"},
    )
    assert resp.status == 200
    await resp.json()


@pytest.mark.asyncio
async def test_protected_routes_require_auth(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        page = await client.get("/pairs", allow_redirects=False)
        assert page.status == 302
        assert page.headers["Location"] == "/login"

        api = await client.get("/api/pairs")
        assert api.status == 401
        payload = await api.json()
        assert payload["error"] == "unauthorized"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_login_logout_and_session_invalidation(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)

        ok = await client.get("/api/pairs")
        assert ok.status == 200

        logout = await client.post("/api/logout")
        assert logout.status == 200

        blocked = await client.get("/api/pairs")
        assert blocked.status == 401
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_crud_and_search_via_api(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)

        create_resp = await client.post(
            "/api/pairs",
            json={
                "name": "customer-internal",
                "group_a_chat_id": -100111,
                "group_b_chat_id": -100222,
                "bidirectional": True,
                "enabled": True,
                "filters": {
                    "types_allow": ["text", "photo"],
                    "keywords_block": ["spam"],
                    "keywords_allow": [],
                },
            },
        )
        assert create_resp.status == 201

        search_resp = await client.get("/api/pairs?q=customer")
        assert search_resp.status == 200
        search_payload = await search_resp.json()
        assert len(search_payload["pairs"]) == 1
        assert search_payload["pairs"][0]["name"] == "customer-internal"

        update_resp = await client.put(
            "/api/pairs/customer-internal",
            json={
                "enabled": False,
                "group_a_chat_id": -100111,
                "group_b_chat_id": -100333,
                "bidirectional": False,
                "filters": {
                    "types_allow": ["text"],
                    "keywords_block": [],
                    "keywords_allow": ["urgent"],
                },
            },
        )
        assert update_resp.status == 200

        filtered = await client.get("/api/pairs?enabled=false&bidirectional=false")
        payload = await filtered.json()
        assert len(payload["pairs"]) == 1
        assert payload["pairs"][0]["enabled"] is False

        delete_resp = await client.delete("/api/pairs/customer-internal")
        assert delete_resp.status == 200

        empty = await client.get("/api/pairs?q=customer")
        empty_payload = await empty.json()
        assert empty_payload["pairs"] == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manual_backup_endpoint_creates_file(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)

        # Ensure there is at least one DB write.
        store = SQLiteConfigStore(db_path)
        store.create_pair(
            PairRecord(
                id=None,
                name="p1",
                group_a_chat_id=-100111,
                group_b_chat_id=-100222,
                bidirectional=True,
                enabled=True,
                filters=PairFilters(
                    types_allow=["text"],
                    keywords_block=[],
                    keywords_allow=[],
                ),
            )
        )

        resp = await client.post("/api/backup")
        assert resp.status == 200
        payload = await resp.json()
        assert payload["success"] is True
        assert payload["backup_path"] is not None
        assert Path(payload["backup_path"]).exists()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_stats_returns_aggregated_counts(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)

        stats_file = tmp_path / "stats.json"
        stats_file.write_text(json.dumps({
            "pair-a": {"date": "2026-06-10", "week_key": "2026-W24", "today": 5, "week": 20},
            "pair-b": {"date": "2026-06-10", "week_key": "2026-W24", "today": 3, "week": 15},
        }))

        resp = await client.get("/api/stats")
        assert resp.status == 200
        data = await resp.json()
        assert data["today"] == 8
        assert data["week"] == 35
        assert "pairs_total" in data
        assert "pairs_active" in data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_stats_returns_zeros_when_no_stats_file(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/api/stats")
        assert resp.status == 200
        data = await resp.json()
        assert data["today"] == 0
        assert data["week"] == 0
    finally:
        await client.close()
