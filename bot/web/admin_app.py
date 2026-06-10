from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import aiohttp_jinja2
import jinja2
from aiohttp import web

from bot.storage.auth_store import AuthStore, verify_password
from bot.storage.backup_ops import create_backup
from bot.storage.config_store import PairFilters, PairRecord, SQLiteConfigStore


SESSION_COOKIE = "admin_session"
DB_PATH_KEY: web.AppKey[str] = web.AppKey("db_path")
CONFIG_STORE_KEY: web.AppKey[SQLiteConfigStore] = web.AppKey("config_store")
AUTH_STORE_KEY: web.AppKey[AuthStore] = web.AppKey("auth_store")
BACKUP_DIR_KEY: web.AppKey[str] = web.AppKey("backup_dir")
BACKUP_RETENTION_DAYS_KEY: web.AppKey[int] = web.AppKey("backup_retention_days")
STATS_PATH_KEY: web.AppKey[str] = web.AppKey("stats_path")


def _to_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_pair(pair: PairRecord) -> dict[str, Any]:
    return {
        "id": pair.id,
        "name": pair.name,
        "group_a_chat_id": pair.group_a_chat_id,
        "group_b_chat_id": pair.group_b_chat_id,
        "bidirectional": pair.bidirectional,
        "enabled": pair.enabled,
        "filters": {
            "types_allow": pair.filters.types_allow,
            "keywords_block": pair.filters.keywords_block,
            "keywords_allow": pair.filters.keywords_allow,
        },
    }


def _pair_from_payload(payload: dict[str, Any], *, pair_id: int | None = None) -> PairRecord:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name is required")

    try:
        group_a_chat_id = int(payload.get("group_a_chat_id"))
        group_b_chat_id = int(payload.get("group_b_chat_id"))
    except (TypeError, ValueError):
        raise ValueError("group chat IDs must be valid integers")

    filters = payload.get("filters", {}) or {}
    types_allow = filters.get("types_allow") or ["text"]
    keywords_block = filters.get("keywords_block") or []
    keywords_allow = filters.get("keywords_allow") or []

    return PairRecord(
        id=pair_id,
        name=name,
        group_a_chat_id=group_a_chat_id,
        group_b_chat_id=group_b_chat_id,
        bidirectional=bool(payload.get("bidirectional", True)),
        enabled=bool(payload.get("enabled", True)),
        filters=PairFilters(
            types_allow=list(types_allow),
            keywords_block=list(keywords_block),
            keywords_allow=list(keywords_allow),
        ),
    )


@web.middleware
async def auth_middleware(request: web.Request, handler):
    public_paths = {"/login", "/api/login"}
    if request.path in public_paths:
        return await handler(request)

    is_protected = request.path.startswith("/pairs") or request.path.startswith("/api")
    if not is_protected:
        return await handler(request)

    auth_store = request.app[AUTH_STORE_KEY]
    session_id = request.cookies.get(SESSION_COOKIE)
    user = auth_store.get_user_by_session(session_id) if session_id else None
    if user is None:
        if request.path.startswith("/api"):
            return web.json_response({"error": "unauthorized"}, status=401)
        raise web.HTTPFound("/login")

    request["user"] = user
    return await handler(request)


async def index_handler(_: web.Request) -> web.StreamResponse:
    raise web.HTTPFound("/pairs")


async def login_page(_: web.Request) -> web.Response:
    html = """
    <html><body>
      <h1>Admin Login</h1>
      <form method="post" action="/api/login">
        <label>Username <input name="username" /></label><br/>
        <label>Password <input type="password" name="password" /></label><br/>
        <button type="submit">Login</button>
      </form>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")


async def api_login(request: web.Request) -> web.StreamResponse:
    auth_store = request.app[AUTH_STORE_KEY]
    if request.content_type.startswith("application/json"):
        payload = await request.json()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
    else:
        form = await request.post()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))

    user = auth_store.get_user_by_username(username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return web.json_response({"error": "invalid_credentials"}, status=401)

    session_id = auth_store.create_session(user.id)
    response = web.json_response({"ok": True, "username": user.username})
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="Lax")
    return response


async def api_logout(request: web.Request) -> web.StreamResponse:
    auth_store = request.app[AUTH_STORE_KEY]
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        auth_store.delete_session(session_id)
    response = web.json_response({"ok": True})
    response.del_cookie(SESSION_COOKIE)
    return response


def _split_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


async def pairs_page(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    q = request.query.get("q")
    chat_raw = request.query.get("chat_id")
    chat_id = int(chat_raw) if chat_raw else None
    enabled_raw = request.query.get("enabled")
    bidir_raw = request.query.get("bidirectional")
    enabled = None if enabled_raw is None or enabled_raw == "" else _to_bool(enabled_raw)
    bidirectional = None if bidir_raw is None or bidir_raw == "" else _to_bool(bidir_raw)
    pairs = store.list_pairs(
        name_query=q,
        chat_id=chat_id,
        enabled=enabled,
        bidirectional=bidirectional,
    )

    rows = "\n".join(
        (
            f"<tr><td>{p.name}</td><td>{p.group_a_chat_id}</td><td>{p.group_b_chat_id}</td>"
            f"<td>{p.enabled}</td><td>{p.bidirectional}</td>"
            f"<td><a href='/pairs/{p.name}/edit'>edit</a></td>"
            f"<td><form method='post' action='/pairs/{p.name}/delete'>"
            f"<button type='submit'>delete</button></form></td></tr>"
        )
        for p in pairs
    )
    html = f"""
    <html><body>
      <h1>Pairs</h1>
      <form method="get" action="/pairs">
        <input name="q" placeholder="name" value="{q or ''}" />
        <input name="chat_id" placeholder="chat id" value="{chat_raw or ''}" />
        <input name="enabled" placeholder="true/false" value="{enabled_raw or ''}" />
        <input name="bidirectional" placeholder="true/false" value="{bidir_raw or ''}" />
        <button type="submit">Search</button>
      </form>
      <p><a href="/pairs/new">Create Pair</a></p>
      <table border="1">
        <tr><th>Name</th><th>A</th><th>B</th><th>Enabled</th><th>Bidir</th><th colspan="2">Actions</th></tr>
        {rows}
      </table>
      <form method="post" action="/api/logout"><button type="submit">Logout</button></form>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")


def _pair_form_html(pair: PairRecord | None = None) -> str:
    if pair is None:
        name = ""
        group_a = ""
        group_b = ""
        bidirectional = True
        enabled = True
        types_allow = "text,photo,video,sticker,document,voice,animation"
        keywords_block = ""
        keywords_allow = ""
    else:
        name = pair.name
        group_a = str(pair.group_a_chat_id)
        group_b = str(pair.group_b_chat_id)
        bidirectional = pair.bidirectional
        enabled = pair.enabled
        types_allow = ",".join(pair.filters.types_allow)
        keywords_block = ",".join(pair.filters.keywords_block)
        keywords_allow = ",".join(pair.filters.keywords_allow)

    return f"""
      <label>Name <input name="name" value="{name}" /></label><br/>
      <label>Group A <input name="group_a_chat_id" value="{group_a}" /></label><br/>
      <label>Group B <input name="group_b_chat_id" value="{group_b}" /></label><br/>
      <label>Bidirectional <input name="bidirectional" value="{str(bidirectional).lower()}" /></label><br/>
      <label>Enabled <input name="enabled" value="{str(enabled).lower()}" /></label><br/>
      <label>Types allow (csv) <input name="types_allow" value="{types_allow}" /></label><br/>
      <label>Keywords block (csv) <input name="keywords_block" value="{keywords_block}" /></label><br/>
      <label>Keywords allow (csv) <input name="keywords_allow" value="{keywords_allow}" /></label><br/>
    """


async def pair_create_page(_: web.Request) -> web.Response:
    html = f"""
    <html><body>
      <h1>Create Pair</h1>
      <form method="post" action="/pairs/new">
        {_pair_form_html(None)}
        <button type="submit">Create</button>
      </form>
      <p><a href="/pairs">Back</a></p>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")


async def pair_edit_page(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    pair = store.get_pair_by_name(name)
    if pair is None:
        return web.Response(status=404, text="pair not found")
    html = f"""
    <html><body>
      <h1>Edit Pair: {pair.name}</h1>
      <form method="post" action="/pairs/{pair.name}/edit">
        {_pair_form_html(pair)}
        <button type="submit">Save</button>
      </form>
      <p><a href="/pairs">Back</a></p>
    </body></html>
    """
    return web.Response(text=html, content_type="text/html")


def _pair_payload_from_form(form: dict[str, str]) -> dict[str, Any]:
    return {
        "name": form.get("name"),
        "group_a_chat_id": form.get("group_a_chat_id"),
        "group_b_chat_id": form.get("group_b_chat_id"),
        "bidirectional": _to_bool(form.get("bidirectional"), default=True),
        "enabled": _to_bool(form.get("enabled"), default=True),
        "filters": {
            "types_allow": _split_csv(form.get("types_allow", "")) or ["text"],
            "keywords_block": _split_csv(form.get("keywords_block", "")),
            "keywords_allow": _split_csv(form.get("keywords_allow", "")),
        },
    }


async def pair_create_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    form = await request.post()
    payload = _pair_payload_from_form(form)
    pair = _pair_from_payload(payload)
    try:
        store.create_pair(pair)
    except ValueError as exc:
        return web.Response(status=400, text=str(exc))
    raise web.HTTPFound("/pairs")


async def pair_edit_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    old_name = request.match_info["name"]
    existing = store.get_pair_by_name(old_name)
    if existing is None:
        return web.Response(status=404, text="pair not found")
    form = await request.post()
    payload = _pair_payload_from_form(form)
    updated = _pair_from_payload(payload, pair_id=existing.id)
    try:
        store.update_pair(updated)
    except ValueError as exc:
        return web.Response(status=400, text=str(exc))
    raise web.HTTPFound("/pairs")


async def pair_delete_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    store.delete_pair(request.match_info["name"])
    raise web.HTTPFound("/pairs")


async def api_list_pairs(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    q = request.query.get("q")
    chat_raw = request.query.get("chat_id")
    chat_id = int(chat_raw) if chat_raw else None
    enabled_raw = request.query.get("enabled")
    bidir_raw = request.query.get("bidirectional")
    enabled = None if enabled_raw is None else _to_bool(enabled_raw)
    bidirectional = None if bidir_raw is None else _to_bool(bidir_raw)
    rows = store.list_pairs(
        name_query=q,
        chat_id=chat_id,
        enabled=enabled,
        bidirectional=bidirectional,
    )
    return web.json_response({"pairs": [_json_pair(row) for row in rows]})


async def api_create_pair(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    payload = await request.json()
    pair = _pair_from_payload(payload)
    try:
        created = store.create_pair(pair)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"pair": _json_pair(created)}, status=201)


async def api_update_pair(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    existing = store.get_pair_by_name(name)
    if existing is None:
        return web.json_response({"error": "pair_not_found"}, status=404)
    payload = await request.json()
    payload["name"] = payload.get("name", existing.name)
    try:
        updated = _pair_from_payload(payload, pair_id=existing.id)
        store.update_pair(updated)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"pair": _json_pair(updated)})


async def api_delete_pair(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    if store.get_pair_by_name(name) is None:
        return web.json_response({"error": "pair_not_found"}, status=404)
    store.delete_pair(name)
    return web.json_response({"ok": True})


async def api_backup_now(request: web.Request) -> web.Response:
    db_path = request.app[DB_PATH_KEY]
    backup_dir = request.app[BACKUP_DIR_KEY]
    retention_days = request.app[BACKUP_RETENTION_DAYS_KEY]
    result = create_backup(
        db_path=db_path,
        backup_dir=backup_dir,
        retention_days=retention_days,
    )
    status = 200 if result.success else 500
    return web.json_response(asdict(result), status=status)


def create_admin_app(
    *,
    db_path: str,
    config_store: SQLiteConfigStore,
    auth_store: AuthStore,
    backup_dir: str = "backups",
    backup_retention_days: int = 30,
    stats_path: str = "data/stats.json",
) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app[DB_PATH_KEY] = db_path
    app[CONFIG_STORE_KEY] = config_store
    app[AUTH_STORE_KEY] = auth_store
    app[BACKUP_DIR_KEY] = backup_dir
    app[BACKUP_RETENTION_DAYS_KEY] = backup_retention_days
    app[STATS_PATH_KEY] = stats_path

    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
    )

    app.router.add_static("/static/", path=str(Path(__file__).parent / "static"), name="static")
    app.router.add_get("/", index_handler)
    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", api_login)
    app.router.add_post("/api/logout", api_logout)
    app.router.add_get("/pairs", pairs_page)
    app.router.add_get("/pairs/new", pair_create_page)
    app.router.add_post("/pairs/new", pair_create_submit)
    app.router.add_get("/pairs/{name}/edit", pair_edit_page)
    app.router.add_post("/pairs/{name}/edit", pair_edit_submit)
    app.router.add_post("/pairs/{name}/delete", pair_delete_submit)
    app.router.add_get("/api/pairs", api_list_pairs)
    app.router.add_post("/api/pairs", api_create_pair)
    app.router.add_put("/api/pairs/{name}", api_update_pair)
    app.router.add_delete("/api/pairs/{name}", api_delete_pair)
    app.router.add_post("/api/backup", api_backup_now)
    return app
