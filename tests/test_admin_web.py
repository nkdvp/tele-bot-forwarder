import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.storage.auth_store import AuthStore
from bot.storage.access_store import AccessStore
from bot.storage.config_store import PairFilters, PairMaskRule, PairRecord, SQLiteConfigStore
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
                "bidirectional": True,
                "filters": {
                    "types_allow": ["text"],
                    "keywords_block": [],
                    "keywords_allow": ["urgent"],
                },
            },
        )
        assert update_resp.status == 200

        filtered = await client.get("/api/pairs?enabled=false&bidirectional=true")
        payload = await filtered.json()
        assert len(payload["pairs"]) == 1
        assert payload["pairs"][0]["enabled"] is False

        one_way_update = await client.put(
            "/api/pairs/customer-internal",
            json={
                "enabled": True,
                "group_a_chat_id": -100111,
                "group_b_chat_id": -100333,
                "bidirectional": False,
                "filters": {
                    "types_allow": ["text"],
                    "keywords_block": [],
                    "keywords_allow": [],
                },
            },
        )
        assert one_way_update.status == 400

        one_way_create = await client.post(
            "/api/pairs",
            json={
                "name": "one-way-not-allowed",
                "group_a_chat_id": -1009911,
                "group_b_chat_id": -1009922,
                "bidirectional": False,
                "enabled": True,
                "filters": {
                    "types_allow": ["text"],
                    "keywords_block": [],
                    "keywords_allow": [],
                },
            },
        )
        assert one_way_create.status == 400
        one_way_payload = await one_way_create.json()
        assert "one-way pairs are currently disabled" in one_way_payload["error"]

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


@pytest.mark.asyncio
async def test_login_page_renders_html(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/login")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Luna" in body
        assert "Đăng nhập" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_login_valid_credentials_redirects(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            allow_redirects=False,
        )
        assert resp.status == 302
        assert resp.headers["Location"] == "/dashboard"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_post_login_invalid_credentials_shows_error(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status == 200
        body = await resp.text()
        assert "Sai tên đăng nhập hoặc mật khẩu" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_dashboard_page_renders_html(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/dashboard")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Tổng quan" in body
        assert "Tổng số cặp" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_dashboard_requires_auth(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/dashboard", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/login"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_index_redirects_to_dashboard(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/dashboard"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pairs_page_renders_pairs(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        store = SQLiteConfigStore(db_path)
        store.create_pair(PairRecord(
            id=None, name="test-pair",
            group_a_chat_id=-100111, group_b_chat_id=-100222,
            bidirectional=True, enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        ))

        resp = await client.get("/pairs")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "test-pair" in body
        assert "Cặp nhóm" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_create_page_renders_form(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.get("/pairs/new")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Tạo cặp" in body
        assert "Chat ID nhóm A" in body
        assert "luôn là hai chiều" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_edit_page_renders_existing_values(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        store = SQLiteConfigStore(db_path)
        store.create_pair(PairRecord(
            id=None, name="edit-me",
            group_a_chat_id=-100111, group_b_chat_id=-100222,
            bidirectional=False, enabled=True,
            filters=PairFilters(types_allow=["text"], keywords_block=["spam"], keywords_allow=[]),
        ))

        resp = await client.get("/pairs/edit-me/edit")
        assert resp.status == 200
        body = await resp.text()
        assert "edit-me" in body
        assert "-100111" in body
        assert "spam" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_form_submit_creates_pair_and_redirects(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.post(
            "/pairs/new",
            data={
                "name": "form-pair",
                "group_a_chat_id": "-100111",
                "group_b_chat_id": "-100222",
                "bidirectional": "true",
                "enabled": "true",
                "types_allow": ["text", "photo"],
                "keywords_block": "spam, ads",
                "keywords_allow": "",
            },
            allow_redirects=False,
        )
        assert resp.status == 302
        assert resp.headers["Location"] == "/pairs"
        store = SQLiteConfigStore(db_path)
        pair = store.get_pair_by_name("form-pair")
        assert pair is not None
        assert pair.group_a_chat_id == -100111
        assert "photo" in pair.filters.types_allow
        assert "spam" in pair.filters.keywords_block
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pair_form_defaults_to_bidirectional_when_checkbox_missing(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)
        resp = await client.post(
            "/pairs/new",
            data={
                "name": "default-bidi",
                "group_a_chat_id": "-1001711",
                "group_b_chat_id": "-1001712",
                "enabled": "true",
                "types_allow": ["text"],
                "keywords_block": "",
                "keywords_allow": "",
            },
            allow_redirects=False,
        )
        assert resp.status == 302
        store = SQLiteConfigStore(db_path)
        pair = store.get_pair_by_name("default-bidi")
        assert pair is not None
        assert pair.bidirectional is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_backups_page_renders_html(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login(client)

        # Create a backup file so the table has a row
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "forwarder-20260610-120000.db").write_bytes(b"x" * 2048)

        resp = await client.get("/backups")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        body = await resp.text()
        assert "Sao lưu" in body
        assert "forwarder-20260610-120000.db" in body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_backups_requires_auth(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        resp = await client.get("/backups", allow_redirects=False)
        assert resp.status == 302
        assert resp.headers["Location"] == "/login"
    finally:
        await client.close()


async def _login_as(client: TestClient, username: str, password: str) -> None:
    resp = await client.post(
        "/api/login",
        json={"username": username, "password": password},
    )
    assert resp.status == 200
    await resp.json()


def _seed_rbac_fixture(db_path: str) -> dict[str, int]:
    auth_store = AuthStore(db_path)
    access_store = AccessStore(db_path)
    config_store = SQLiteConfigStore(db_path)

    manager = auth_store.create_user(username="manager", password="pw-manager", global_role="user")
    viewer = auth_store.create_user(username="viewer", password="pw-viewer", global_role="user")
    outsider = auth_store.create_user(username="outsider", password="pw-outsider", global_role="user")
    second_admin = auth_store.create_user(username="admin2", password="pw-admin2", global_role="admin")

    team_a = access_store.create_team("Team A")
    team_b = access_store.create_team("Team B")
    access_store.upsert_team_member(team_id=team_a.id, user_id=manager.id, role="manager")
    access_store.upsert_team_member(team_id=team_a.id, user_id=viewer.id, role="viewer")
    access_store.upsert_team_member(team_id=team_b.id, user_id=outsider.id, role="owner")

    pair_a = config_store.create_pair(PairRecord(
        id=None,
        name="pair-a",
        group_a_chat_id=-1001001,
        group_b_chat_id=-1001002,
        bidirectional=True,
        enabled=True,
        filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        team_id=team_a.id,
        created_by_user_id=manager.id,
    ))
    pair_b = config_store.create_pair(PairRecord(
        id=None,
        name="pair-b",
        group_a_chat_id=-1002001,
        group_b_chat_id=-1002002,
        bidirectional=True,
        enabled=True,
        filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
        team_id=team_b.id,
        created_by_user_id=outsider.id,
    ))

    return {
        "manager_id": manager.id,
        "viewer_id": viewer.id,
        "outsider_id": outsider.id,
        "admin2_id": second_admin.id,
        "team_a_id": team_a.id,
        "team_b_id": team_b.id,
        "pair_a_id": pair_a.id or 0,
        "pair_b_id": pair_b.id or 0,
    }


@pytest.mark.asyncio
async def test_rbac_team_scoping_and_super_admin_visibility(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        _seed_rbac_fixture(db_path)

        await _login_as(client, "admin", "secret")
        admin_pairs = await client.get("/api/pairs")
        admin_payload = await admin_pairs.json()
        assert {p["name"] for p in admin_payload["pairs"]} >= {"pair-a", "pair-b"}
        await client.post("/api/logout")

        await _login_as(client, "viewer", "pw-viewer")
        viewer_pairs = await client.get("/api/pairs")
        viewer_payload = await viewer_pairs.json()
        assert [p["name"] for p in viewer_payload["pairs"]] == ["pair-a"]
        await client.post("/api/logout")

        await _login_as(client, "admin2", "pw-admin2")
        admin2_pairs = await client.get("/api/pairs")
        admin2_payload = await admin2_pairs.json()
        assert admin2_payload["pairs"] == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_sidebar_navigation_visibility_matches_global_role(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        _seed_rbac_fixture(db_path)

        await _login_as(client, "viewer", "pw-viewer")
        viewer_page = await client.get("/pairs")
        viewer_body = await viewer_page.text()
        assert 'href="/backups"' not in viewer_body
        assert 'href="/users"' not in viewer_body
        assert 'href="/teams"' not in viewer_body
        await client.post("/api/logout")

        await _login_as(client, "admin", "secret")
        admin_page = await client.get("/pairs")
        admin_body = await admin_page.text()
        assert 'href="/backups"' in admin_body
        assert 'href="/users"' in admin_body
        assert 'href="/teams"' in admin_body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_viewer_cannot_mutate_pairs_or_masks(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        fixture = _seed_rbac_fixture(db_path)
        await _login_as(client, "viewer", "pw-viewer")

        edit_page = await client.get("/pairs/pair-a/edit")
        assert edit_page.status == 200

        update_resp = await client.put(
            "/api/pairs/pair-a",
            json={
                "group_a_chat_id": -1001001,
                "group_b_chat_id": -1001002,
                "bidirectional": True,
                "enabled": False,
                "team_id": fixture["team_a_id"],
                "filters": {"types_allow": ["text"], "keywords_block": [], "keywords_allow": []},
            },
        )
        assert update_resp.status == 403

        mask_resp = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "10101",
                "direction": "a_to_b",
                "mode": "alias",
                "alias": "Masked Name",
            },
            allow_redirects=False,
        )
        assert mask_resp.status == 403

        backup_resp = await client.post("/api/backup")
        assert backup_resp.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_manager_can_manage_own_team_only(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        fixture = _seed_rbac_fixture(db_path)
        await _login_as(client, "manager", "pw-manager")

        create_own = await client.post(
            "/api/pairs",
            json={
                "name": "manager-own",
                "group_a_chat_id": -1003011,
                "group_b_chat_id": -1003012,
                "bidirectional": True,
                "enabled": True,
                "team_id": fixture["team_a_id"],
                "filters": {"types_allow": ["text"], "keywords_block": [], "keywords_allow": []},
            },
        )
        assert create_own.status == 201

        create_other = await client.post(
            "/api/pairs",
            json={
                "name": "manager-other",
                "group_a_chat_id": -1004011,
                "group_b_chat_id": -1004012,
                "bidirectional": True,
                "enabled": True,
                "team_id": fixture["team_b_id"],
                "filters": {"types_allow": ["text"], "keywords_block": [], "keywords_allow": []},
            },
        )
        assert create_other.status == 403

        cross_team = await client.get("/pairs/pair-b/edit")
        assert cross_team.status == 403
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_api_pairs_pagination_defaults_and_page_sizes(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        await _login_as(client, "admin", "secret")
        store = SQLiteConfigStore(db_path)
        for idx in range(55):
            store.create_pair(
                PairRecord(
                    id=None,
                    name=f"pair-{idx:03d}",
                    group_a_chat_id=-1010000 - idx * 2,
                    group_b_chat_id=-1010001 - idx * 2,
                    bidirectional=True,
                    enabled=True,
                    filters=PairFilters(types_allow=["text"], keywords_block=[], keywords_allow=[]),
                )
            )

        default_page = await client.get("/api/pairs")
        default_payload = await default_page.json()
        assert default_payload["pagination"]["page_size"] == 20
        assert len(default_payload["pairs"]) == 20

        page_50 = await client.get("/api/pairs?page_size=50")
        payload_50 = await page_50.json()
        assert payload_50["pagination"]["page_size"] == 50
        assert len(payload_50["pairs"]) == 50

        page_100 = await client.get("/api/pairs?page_size=100")
        payload_100 = await page_100.json()
        assert payload_100["pagination"]["page_size"] == 100
        assert len(payload_100["pairs"]) == 55

        invalid_size = await client.get("/api/pairs?page_size=999")
        invalid_payload = await invalid_size.json()
        assert invalid_payload["pagination"]["page_size"] == 20

        page_2 = await client.get("/api/pairs?page=2&page_size=20")
        page_2_payload = await page_2.json()
        assert page_2_payload["pagination"]["page"] == 2
        assert len(page_2_payload["pairs"]) == 20
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mask_rules_and_alias_suggestions_respect_permissions(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        fixture = _seed_rbac_fixture(db_path)
        await _login_as(client, "manager", "pw-manager")
        store = SQLiteConfigStore(db_path)

        create_alias = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "9001",
                "mode": "alias",
                "alias": "Customer Alpha",
            },
            allow_redirects=False,
        )
        assert create_alias.status == 302
        pair_a_rules = store.list_pair_mask_rules(fixture["pair_a_id"])
        directions = {rule.direction for rule in pair_a_rules if rule.telegram_user_id == 9001}
        assert directions == {"a_to_b", "b_to_a"}

        create_anonymous = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "9002",
                "mode": "anonymous",
                "alias": "",
            },
            allow_redirects=False,
        )
        assert create_anonymous.status == 302
        anon_rules = [
            rule
            for rule in store.list_pair_mask_rules(fixture["pair_a_id"])
            if rule.telegram_user_id == 9002
        ]
        assert len(anon_rules) == 2
        assert {rule.direction for rule in anon_rules} == {"a_to_b", "b_to_a"}
        assert all(rule.mode == "anonymous" for rule in anon_rules)
        assert all(rule.alias is None for rule in anon_rules)

        missing_alias = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "9001",
                "mode": "alias",
                "alias": "",
            },
        )
        assert missing_alias.status == 200
        assert "alias is required" in await missing_alias.text()

        aliases_resp = await client.get("/api/mask-aliases?telegram_user_id=9001")
        aliases_payload = await aliases_resp.json()
        assert aliases_payload["aliases"] == ["Customer Alpha"]

        # Regression for real-world payload path reported by user.
        create_alias_real_payload = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "2043771174",
                "mode": "alias",
                "alias": "ss",
            },
            allow_redirects=False,
        )
        assert create_alias_real_payload.status == 302
        real_rules = [
            rule
            for rule in store.list_pair_mask_rules(fixture["pair_a_id"])
            if rule.telegram_user_id == 2043771174
        ]
        assert len(real_rules) == 2
        assert {rule.direction for rule in real_rules} == {"a_to_b", "b_to_a"}
        assert all(rule.mode == "alias" and rule.alias == "ss" for rule in real_rules)

        store.upsert_pair_mask_rule(
            PairMaskRule(
                id=None,
                pair_id=fixture["pair_b_id"],
                telegram_user_id=990099,
                direction="a_to_b",
                mode="alias",
                alias="Other Team Name",
            )
        )
        cross_delete = await client.post(
            "/pairs/pair-a/masks/990099/delete",
            allow_redirects=False,
        )
        assert cross_delete.status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_language_switch_persists_for_follow_up_pages(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)
        vi_page = await client.get("/pairs")
        vi_body = await vi_page.text()
        assert "Cặp nhóm" in vi_body

        en_page = await client.get("/pairs?lang=en")
        en_body = await en_page.text()
        assert "Pairs" in en_body

        persisted_page = await client.get("/pairs")
        persisted_body = await persisted_page.text()
        assert "Pairs" in persisted_body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_theme_switch_persists_for_follow_up_pages(tmp_path):
    client, _ = await _make_client(tmp_path)
    try:
        await _login(client)

        default_page = await client.get("/pairs")
        default_body = await default_page.text()
        assert 'data-theme="dark"' in default_body

        light_page = await client.get("/pairs?theme=light")
        light_body = await light_page.text()
        assert 'data-theme="light"' in light_body

        persisted_page = await client.get("/pairs")
        persisted_body = await persisted_page.text()
        assert 'data-theme="light"' in persisted_body
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mask_table_renders_single_row_per_user_mapping(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        fixture = _seed_rbac_fixture(db_path)
        await _login_as(client, "manager", "pw-manager")
        store = SQLiteConfigStore(db_path)

        create_alias = await client.post(
            "/pairs/pair-a/masks",
            data={
                "telegram_user_id": "8080",
                "mode": "alias",
                "alias": "One Row Alias",
            },
            allow_redirects=False,
        )
        assert create_alias.status == 302

        resp = await client.get("/pairs/pair-a/edit")
        body = await resp.text()
        assert body.count('<span class="td-muted">8080</span>') == 1
        assert "One Row Alias" in body

        delete_resp = await client.post(
            "/pairs/pair-a/masks/8080/delete",
            allow_redirects=False,
        )
        assert delete_resp.status == 302
        remaining = [
            rule for rule in store.list_pair_mask_rules(fixture["pair_a_id"])
            if rule.telegram_user_id == 8080
        ]
        assert remaining == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_users_and_teams_admin_safety_rules(tmp_path):
    client, db_path = await _make_client(tmp_path)
    try:
        fixture = _seed_rbac_fixture(db_path)
        admin_id = AuthStore(db_path).get_user_by_username("admin").id

        await _login_as(client, "admin2", "pw-admin2")
        forbidden_grant = await client.post(
            "/users",
            data={
                "username": "cannot-grant",
                "password": "pw",
                "global_role": "super_admin",
                "is_active": "true",
            },
            allow_redirects=False,
        )
        assert forbidden_grant.status == 403
        await client.post("/api/logout")

        await _login_as(client, "admin", "secret")
        team_rename = await client.post(
            f"/teams/{fixture['team_a_id']}/edit",
            data={"name": "Team Alpha"},
            allow_redirects=False,
        )
        assert team_rename.status == 302

        team_delete_blocked = await client.post(
            f"/teams/{fixture['team_a_id']}/delete",
            allow_redirects=False,
        )
        assert team_delete_blocked.status == 200
        assert "Cannot delete team with assigned pairs" in await team_delete_blocked.text()

        disable_last_super = await client.post(
            f"/users/{admin_id}/edit",
            data={"global_role": "admin", "is_active": "true"},
        )
        assert disable_last_super.status == 200
        assert "cannot remove the last active super_admin" in await disable_last_super.text()

        self_delete = await client.post(f"/users/{admin_id}/delete")
        assert self_delete.status == 200
        assert "cannot delete your own account" in await self_delete.text()

        remove_admin2 = await client.post(
            f"/users/{fixture['admin2_id']}/delete",
            allow_redirects=False,
        )
        assert remove_admin2.status == 302
    finally:
        await client.close()
