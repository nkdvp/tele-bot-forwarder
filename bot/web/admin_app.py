from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp_jinja2
import jinja2
from aiohttp import web

from bot.storage.access_store import AccessStore
from bot.storage.auth_store import AuthStore, verify_password
from bot.storage.backup_ops import create_backup
from bot.storage.config_store import PairFilters, PairMaskRule, PairRecord, SQLiteConfigStore


SESSION_COOKIE = "admin_session"
LOCALE_COOKIE = "admin_locale"
THEME_COOKIE = "admin_theme"
DEFAULT_LOCALE = "vi"
DEFAULT_THEME = "dark"
SUPPORTED_LOCALES = {"vi", "en"}
SUPPORTED_THEMES = {"dark", "light"}
DB_PATH_KEY: web.AppKey[str] = web.AppKey("db_path")
CONFIG_STORE_KEY: web.AppKey[SQLiteConfigStore] = web.AppKey("config_store")
AUTH_STORE_KEY: web.AppKey[AuthStore] = web.AppKey("auth_store")
ACCESS_STORE_KEY: web.AppKey[AccessStore] = web.AppKey("access_store")
BACKUP_DIR_KEY: web.AppKey[str] = web.AppKey("backup_dir")
BACKUP_RETENTION_DAYS_KEY: web.AppKey[int] = web.AppKey("backup_retention_days")
STATS_PATH_KEY: web.AppKey[str] = web.AppKey("stats_path")
PAGE_SIZE_OPTIONS = [20, 50, 100]
# Keep one-way capability in code, but disable it in UI/API for now.
ALLOW_ONE_WAY_PAIRS = False

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "nav.dashboard": "Dashboard",
        "nav.pairs": "Pairs",
        "nav.users": "Users",
        "nav.teams": "Teams",
        "nav.backups": "Backups",
        "topbar.logout": "Logout",
        "prefs.language": "Language",
        "prefs.theme": "Theme",
        "prefs.lang_vi": "Tiếng Việt",
        "prefs.lang_en": "English",
        "prefs.theme_dark": "Dark",
        "prefs.theme_light": "Light",
        "toast.delete_success": 'Pair "{name}" deleted',
        "toast.delete_failed": "Delete failed",
        "toast.request_failed": "Request failed",
        "toast.update_failed": "Could not update pair",
        "toast.backup_created": "Backup created: {filename}",
        "toast.backup_failed": "Backup failed",
        "common.cancel": "Cancel",
        "common.delete": "Delete",
        "common.edit": "Edit",
        "common.save": "Save",
        "common.previous": "Previous",
        "common.next": "Next",
        "common.page": "Page",
        "dashboard.title": "Dashboard",
        "dashboard.total_pairs": "Total Pairs",
        "dashboard.active_pairs": "Active Pairs",
        "dashboard.messages_today": "Messages Today",
        "dashboard.messages_week": "Messages This Week",
        "dashboard.system": "System",
        "dashboard.storage": "Storage",
        "dashboard.db_mode": "DB Mode",
        "dashboard.last_backup": "Last Backup",
        "dashboard.never": "Never",
        "dashboard.status": "Status",
        "dashboard.running": "Running",
        "login.title": "Login",
        "login.subtitle": "Admin Dashboard",
        "login.username": "Username",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.invalid_credentials": "Invalid username or password",
        "pairs.title": "Pairs",
        "pairs.search_name": "Search by name…",
        "pairs.chat_id": "Chat ID",
        "pairs.any_status": "Any status",
        "pairs.enabled": "Enabled",
        "pairs.disabled": "Disabled",
        "pairs.any_direction": "Any direction",
        "pairs.bidirectional": "Bidirectional",
        "pairs.one_way": "One-way",
        "pairs.rows": "rows",
        "pairs.search_btn": "Search",
        "pairs.clear": "Clear",
        "pairs.new": "New Pair",
        "pairs.name": "Name",
        "pairs.group_a": "Group A",
        "pairs.group_b": "Group B",
        "pairs.team": "Team",
        "pairs.direction": "Direction",
        "pairs.status": "Status",
        "pairs.actions": "Actions",
        "pairs.empty": "No pairs configured yet.",
        "pairs.create_first": "Create your first pair",
        "pairs.showing": "Showing",
        "pairs.of": "of",
        "pairs.delete_title": "Delete pair?",
        "pairs.delete_confirm_prefix": "Are you sure you want to delete",
        "pairs.delete_confirm_suffix": "This action cannot be undone.",
        "pair_form.new_title": "New Pair",
        "pair_form.edit_title": "Edit Pair",
        "pair_form.name": "Pair Name",
        "pair_form.name_placeholder": "e.g. customer-internal",
        "pair_form.name_hint": "Name cannot be changed after creation.",
        "pair_form.team": "Team",
        "pair_form.group_a": "Group A Chat ID",
        "pair_form.group_b": "Group B Chat ID",
        "pair_form.direction": "Direction",
        "pair_form.direction_hint": "Bidirectional is required by current policy.",
        "pair_form.enabled": "Enabled",
        "pair_form.enabled_hint": "Active forwarding",
        "pair_form.allowed_types": "Allowed Message Types",
        "pair_form.keywords_block": "Keywords - Block List",
        "pair_form.keywords_block_placeholder": "spam, ads, promo",
        "pair_form.keywords_block_hint": "Comma-separated. Messages containing these words are blocked.",
        "pair_form.keywords_allow": "Keywords - Allow List",
        "pair_form.keywords_allow_placeholder": "Leave empty to allow all",
        "pair_form.keywords_allow_hint": "Comma-separated. If non-empty, only messages with these words pass.",
        "pair_form.save": "Save changes",
        "pair_form.create": "Create pair",
        "pair_form.masking_title": "Masking",
        "pair_form.mask_user_id": "Telegram User ID",
        "pair_form.mask_output": "Masked Output",
        "pair_form.mask_anonymous": "Anonymous (User #N)",
        "pair_form.mask_alias_placeholder": "Alias",
        "pair_form.mask_empty": "No mask rules configured for this pair.",
        "pair_form.mask_mode": "Mode",
        "pair_form.mask_mode_alias": "Alias",
        "pair_form.mask_mode_anon": "Anonymous",
        "pair_form.mask_alias_label": "Alias",
        "pair_form.mask_hint_bidirectional": "Mask rules are applied in both directions by default.",
        "pair_form.mask_save": "Save mask",
        "backups.title": "Backups",
        "backups.create_now": "Create backup now",
        "backups.creating": "Creating…",
        "backups.filename": "Filename",
        "backups.size": "Size",
        "backups.created": "Created",
        "backups.empty": "No backups yet. Use the button above to create your first backup.",
        "users.title": "Users",
        "users.username": "Username",
        "users.password": "Password",
        "users.role": "Role",
        "users.role_user": "User",
        "users.role_admin": "Admin",
        "users.role_super_admin": "Super admin",
        "users.active": "Active",
        "users.create": "Create user",
        "users.status": "Status",
        "users.reset_password": "Reset Password",
        "users.actions": "Actions",
        "teams.title": "Teams",
        "teams.team_name": "Team Name",
        "teams.create": "Create team",
        "teams.members": "Members",
        "teams.rename": "Rename Team",
        "teams.delete_team": "Delete team",
        "teams.delete_blocked": "Cannot delete team while pairs are assigned.",
        "teams.team_role": "Team Role",
        "teams.role_viewer": "Viewer",
        "teams.role_manager": "Manager",
        "teams.role_owner": "Owner",
        "teams.add_or_update_member": "Add or update member",
        "teams.remove": "Remove",
        "teams.empty_members": "No members assigned to this team.",
    },
    "vi": {
        "nav.dashboard": "Tổng quan",
        "nav.pairs": "Cặp nhóm",
        "nav.users": "Người dùng",
        "nav.teams": "Nhóm",
        "nav.backups": "Sao lưu",
        "topbar.logout": "Đăng xuất",
        "prefs.language": "Ngôn ngữ",
        "prefs.theme": "Giao diện",
        "prefs.lang_vi": "Tiếng Việt",
        "prefs.lang_en": "English",
        "prefs.theme_dark": "Tối",
        "prefs.theme_light": "Sáng",
        "toast.delete_success": 'Đã xóa cặp "{name}"',
        "toast.delete_failed": "Xóa thất bại",
        "toast.request_failed": "Yêu cầu thất bại",
        "toast.update_failed": "Không thể cập nhật cặp",
        "toast.backup_created": "Đã tạo bản sao lưu: {filename}",
        "toast.backup_failed": "Sao lưu thất bại",
        "common.cancel": "Hủy",
        "common.delete": "Xóa",
        "common.edit": "Sửa",
        "common.save": "Lưu",
        "common.previous": "Trước",
        "common.next": "Tiếp",
        "common.page": "Trang",
        "dashboard.title": "Tổng quan",
        "dashboard.total_pairs": "Tổng số cặp",
        "dashboard.active_pairs": "Cặp đang hoạt động",
        "dashboard.messages_today": "Tin nhắn hôm nay",
        "dashboard.messages_week": "Tin nhắn tuần này",
        "dashboard.system": "Hệ thống",
        "dashboard.storage": "Lưu trữ",
        "dashboard.db_mode": "Chế độ DB",
        "dashboard.last_backup": "Lần sao lưu gần nhất",
        "dashboard.never": "Chưa có",
        "dashboard.status": "Trạng thái",
        "dashboard.running": "Đang chạy",
        "login.title": "Đăng nhập",
        "login.subtitle": "Trang quản trị",
        "login.username": "Tên đăng nhập",
        "login.password": "Mật khẩu",
        "login.submit": "Đăng nhập",
        "login.invalid_credentials": "Sai tên đăng nhập hoặc mật khẩu",
        "pairs.title": "Cặp nhóm",
        "pairs.search_name": "Tìm theo tên…",
        "pairs.chat_id": "Chat ID",
        "pairs.any_status": "Mọi trạng thái",
        "pairs.enabled": "Bật",
        "pairs.disabled": "Tắt",
        "pairs.any_direction": "Mọi hướng",
        "pairs.bidirectional": "Hai chiều",
        "pairs.one_way": "Một chiều",
        "pairs.rows": "dòng",
        "pairs.search_btn": "Tìm",
        "pairs.clear": "Xóa lọc",
        "pairs.new": "Tạo cặp",
        "pairs.name": "Tên",
        "pairs.group_a": "Nhóm A",
        "pairs.group_b": "Nhóm B",
        "pairs.team": "Nhóm",
        "pairs.direction": "Hướng",
        "pairs.status": "Trạng thái",
        "pairs.actions": "Thao tác",
        "pairs.empty": "Chưa có cặp nào.",
        "pairs.create_first": "Tạo cặp đầu tiên",
        "pairs.showing": "Hiển thị",
        "pairs.of": "trên",
        "pairs.delete_title": "Xóa cặp?",
        "pairs.delete_confirm_prefix": "Bạn có chắc muốn xóa",
        "pairs.delete_confirm_suffix": "Hành động này không thể hoàn tác.",
        "pair_form.new_title": "Tạo cặp",
        "pair_form.edit_title": "Sửa cặp",
        "pair_form.name": "Tên cặp",
        "pair_form.name_placeholder": "vd: customer-internal",
        "pair_form.name_hint": "Tên không thể đổi sau khi tạo.",
        "pair_form.team": "Nhóm",
        "pair_form.group_a": "Chat ID nhóm A",
        "pair_form.group_b": "Chat ID nhóm B",
        "pair_form.direction": "Hướng",
        "pair_form.direction_hint": "Theo chính sách hiện tại, luôn là hai chiều.",
        "pair_form.enabled": "Bật",
        "pair_form.enabled_hint": "Chuyển tiếp đang hoạt động",
        "pair_form.allowed_types": "Loại tin nhắn được phép",
        "pair_form.keywords_block": "Từ khóa - Chặn",
        "pair_form.keywords_block_placeholder": "spam, quảng cáo",
        "pair_form.keywords_block_hint": "Phân tách bằng dấu phẩy. Tin chứa các từ này sẽ bị chặn.",
        "pair_form.keywords_allow": "Từ khóa - Cho phép",
        "pair_form.keywords_allow_placeholder": "Để trống để cho phép tất cả",
        "pair_form.keywords_allow_hint": "Phân tách bằng dấu phẩy. Nếu không rỗng, chỉ tin chứa các từ này mới được qua.",
        "pair_form.save": "Lưu thay đổi",
        "pair_form.create": "Tạo cặp",
        "pair_form.masking_title": "Ẩn danh",
        "pair_form.mask_user_id": "Telegram User ID",
        "pair_form.mask_output": "Tên hiển thị sau khi ẩn",
        "pair_form.mask_anonymous": "Ẩn danh (User #N)",
        "pair_form.mask_alias_placeholder": "Bí danh",
        "pair_form.mask_empty": "Chưa có cấu hình ẩn danh cho cặp này.",
        "pair_form.mask_mode": "Chế độ",
        "pair_form.mask_mode_alias": "Bí danh",
        "pair_form.mask_mode_anon": "Ẩn danh",
        "pair_form.mask_alias_label": "Bí danh",
        "pair_form.mask_hint_bidirectional": "Quy tắc ẩn danh mặc định áp dụng hai chiều.",
        "pair_form.mask_save": "Lưu ẩn danh",
        "backups.title": "Sao lưu",
        "backups.create_now": "Tạo sao lưu ngay",
        "backups.creating": "Đang tạo…",
        "backups.filename": "Tên file",
        "backups.size": "Kích thước",
        "backups.created": "Thời gian tạo",
        "backups.empty": "Chưa có bản sao lưu. Dùng nút bên trên để tạo bản sao lưu đầu tiên.",
        "users.title": "Người dùng",
        "users.username": "Tên đăng nhập",
        "users.password": "Mật khẩu",
        "users.role": "Vai trò",
        "users.role_user": "Người dùng",
        "users.role_admin": "Quản trị",
        "users.role_super_admin": "Siêu quản trị",
        "users.active": "Kích hoạt",
        "users.create": "Tạo người dùng",
        "users.status": "Trạng thái",
        "users.reset_password": "Đặt lại mật khẩu",
        "users.actions": "Thao tác",
        "teams.title": "Nhóm",
        "teams.team_name": "Tên nhóm",
        "teams.create": "Tạo nhóm",
        "teams.members": "Thành viên",
        "teams.rename": "Đổi tên nhóm",
        "teams.delete_team": "Xóa nhóm",
        "teams.delete_blocked": "Không thể xóa nhóm khi còn cặp được gán.",
        "teams.team_role": "Vai trò trong nhóm",
        "teams.role_viewer": "Chỉ xem",
        "teams.role_manager": "Quản lý",
        "teams.role_owner": "Chủ nhóm",
        "teams.add_or_update_member": "Thêm hoặc cập nhật thành viên",
        "teams.remove": "Gỡ",
        "teams.empty_members": "Chưa có thành viên nào trong nhóm này.",
    },
}


def _to_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_locale(request: web.Request) -> str:
    query_locale = request.query.get("lang", "").strip().lower()
    if query_locale in SUPPORTED_LOCALES:
        return query_locale
    cookie_locale = request.cookies.get(LOCALE_COOKIE, "").strip().lower()
    if cookie_locale in SUPPORTED_LOCALES:
        return cookie_locale
    return DEFAULT_LOCALE


def _resolve_theme(request: web.Request) -> str:
    query_theme = request.query.get("theme", "").strip().lower()
    if query_theme in SUPPORTED_THEMES:
        return query_theme
    cookie_theme = request.cookies.get(THEME_COOKIE, "").strip().lower()
    if cookie_theme in SUPPORTED_THEMES:
        return cookie_theme
    return DEFAULT_THEME


def _translate(locale: str, key: str) -> str:
    return (
        TRANSLATIONS.get(locale, {}).get(
            key,
            TRANSLATIONS["en"].get(key, key),
        )
    )


def _ui_messages(locale: str) -> dict[str, str]:
    return {
        "deleteSuccess": _translate(locale, "toast.delete_success"),
        "deleteFailed": _translate(locale, "toast.delete_failed"),
        "requestFailed": _translate(locale, "toast.request_failed"),
        "updateFailed": _translate(locale, "toast.update_failed"),
        "backupCreated": _translate(locale, "toast.backup_created"),
        "backupFailed": _translate(locale, "toast.backup_failed"),
    }


def _url_with_query(request: web.Request, **updates: str | None) -> str:
    query = dict(request.query)
    for key, value in updates.items():
        if value is None or value == "":
            query.pop(key, None)
        else:
            query[key] = value
    if not query:
        return request.path
    return f"{request.path}?{urlencode(query)}"


def _render_template(name: str, request: web.Request, context: dict[str, Any]) -> web.Response:
    locale = request["locale"]
    theme = request["theme"]
    context = dict(context)
    context.setdefault("locale", locale)
    context.setdefault("theme", theme)
    context.setdefault("t", lambda key: _translate(locale, key))
    context.setdefault("url_with", lambda **updates: _url_with_query(request, **updates))
    context.setdefault(
        "ui_messages_json",
        json.dumps(_ui_messages(locale), ensure_ascii=False),
    )
    return aiohttp_jinja2.render_template(name, request, context)


def _set_preference_cookies(request: web.Request, response: web.StreamResponse) -> web.StreamResponse:
    response.set_cookie(LOCALE_COOKIE, request["locale"], samesite="Lax")
    response.set_cookie(THEME_COOKIE, request["theme"], samesite="Lax")
    return response


def _json_pair(pair: PairRecord) -> dict[str, Any]:
    return {
        "id": pair.id,
        "name": pair.name,
        "group_a_chat_id": pair.group_a_chat_id,
        "group_b_chat_id": pair.group_b_chat_id,
        "bidirectional": pair.bidirectional,
        "enabled": pair.enabled,
        "team_id": pair.team_id,
        "created_by_user_id": pair.created_by_user_id,
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
        team_id=int(payload["team_id"]) if payload.get("team_id") else None,
        created_by_user_id=(
            int(payload["created_by_user_id"])
            if payload.get("created_by_user_id")
            else None
        ),
    )


def _enforce_bidirectional_policy(
    payload: dict[str, Any],
    *,
    existing_pair: PairRecord | None = None,
) -> None:
    if ALLOW_ONE_WAY_PAIRS:
        return
    requested = bool(payload.get("bidirectional", True))
    if existing_pair is not None and not existing_pair.bidirectional:
        # Preserve legacy one-way pairs; policy only blocks creating/changing into one-way.
        payload["bidirectional"] = False
        return
    if not requested:
        raise ValueError("one-way pairs are currently disabled")
    payload["bidirectional"] = True


def _can_manage_admin_area(request: web.Request) -> bool:
    return request["user"].global_role in {"super_admin", "admin"}


def _accessible_team_ids(request: web.Request) -> list[int] | None:
    return request.app[ACCESS_STORE_KEY].accessible_team_ids(request["user"])


def _can_write_team(request: web.Request, team_id: int | None) -> bool:
    return request.app[ACCESS_STORE_KEY].can_write_team(request["user"], team_id)


def _assert_pair_visible(request: web.Request, pair: PairRecord) -> None:
    team_ids = _accessible_team_ids(request)
    if team_ids is not None and pair.team_id not in team_ids:
        raise web.HTTPForbidden(text="pair not allowed")


def _assert_pair_writable(request: web.Request, pair: PairRecord) -> None:
    _assert_pair_visible(request, pair)
    if not _can_write_team(request, pair.team_id):
        raise web.HTTPForbidden(text="pair not writable")


def _parse_page_params(request: web.Request) -> tuple[int, int]:
    try:
        page = int(request.query.get("page", "1"))
    except ValueError:
        page = 1
    try:
        page_size = int(request.query.get("page_size", "20"))
    except ValueError:
        page_size = 20
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = 20
    return max(page, 1), page_size


def _first_writable_team_id(request: web.Request) -> int | None:
    teams = request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"])
    if not teams:
        return None
    return teams[0].id


def _team_name_map(request: web.Request) -> dict[int, str]:
    return {team.id: team.name for team in request.app[ACCESS_STORE_KEY].list_teams(request["user"])}


def _can_grant_super_admin(request: web.Request) -> bool:
    return request["user"].global_role == "super_admin"


@web.middleware
async def ui_preferences_middleware(request: web.Request, handler):
    request["locale"] = _resolve_locale(request)
    request["theme"] = _resolve_theme(request)
    response = await handler(request)
    return _set_preference_cookies(request, response)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    public_paths = {"/login", "/api/login"}
    if request.path in public_paths:
        return await handler(request)

    is_protected = (
        request.path.startswith("/pairs")
        or request.path.startswith("/api")
        or request.path in {"/dashboard", "/backups", "/users", "/teams"}
        or request.path.startswith("/users/")
        or request.path.startswith("/teams/")
    )
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
    raise web.HTTPFound("/dashboard")


async def dashboard_page(request: web.Request) -> web.Response:
    stats_path = request.app[STATS_PATH_KEY]
    try:
        with open(stats_path) as f:
            raw: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    store = request.app[CONFIG_STORE_KEY]
    pairs = store.list_pairs(team_ids=_accessible_team_ids(request))
    backup_dir = request.app[BACKUP_DIR_KEY]

    return _render_template("dashboard.html", request, {
        "active_page": "dashboard",
        "user": request["user"],
        "today": sum(v.get("today", 0) for v in raw.values()),
        "week": sum(v.get("week", 0) for v in raw.values()),
        "pairs_total": len(pairs),
        "pairs_active": sum(1 for p in pairs if p.enabled),
        "last_backup": _get_last_backup(backup_dir),
    })


async def login_page(request: web.Request) -> web.Response:
    return _render_template("login.html", request, {"error": None})


async def post_login(request: web.Request) -> web.StreamResponse:
    auth_store = request.app[AUTH_STORE_KEY]
    form = await request.post()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    user = auth_store.get_user_by_username(username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return _render_template(
            "login.html",
            request,
            {"error": _translate(request["locale"], "login.invalid_credentials")},
        )

    session_id = auth_store.create_session(user.id)
    response = web.HTTPFound("/dashboard")
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="Lax")
    raise response


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


def _get_last_backup(backup_dir: str) -> str | None:
    p = Path(backup_dir)
    if not p.exists():
        return None
    files = sorted(p.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return None
    return datetime.fromtimestamp(files[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _list_backups(backup_dir: str) -> list[dict]:
    p = Path(backup_dir)
    if not p.exists():
        return []
    result = []
    for f in sorted(p.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
        size = f.stat().st_size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        result.append({
            "name": f.name,
            "size": size_str,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def _aggregate_pair_masks(mask_rules: list[PairMaskRule]) -> list[dict[str, Any]]:
    by_user: dict[int, dict[str, Any]] = {}
    for rule in sorted(mask_rules, key=lambda row: (row.telegram_user_id, row.direction)):
        entry = by_user.setdefault(
            rule.telegram_user_id,
            {
                "telegram_user_id": rule.telegram_user_id,
                "mode": rule.mode,
                "alias": rule.alias,
                "conflict": False,
            },
        )
        if (
            entry["mode"] != rule.mode
            or (entry["alias"] or "") != (rule.alias or "")
        ):
            entry["conflict"] = True
    return list(by_user.values())


async def backups_page(request: web.Request) -> web.Response:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="backups not allowed")
    backup_dir = request.app[BACKUP_DIR_KEY]
    return _render_template("backups.html", request, {
        "active_page": "backups",
        "user": request["user"],
        "backups": _list_backups(backup_dir),
    })


async def pairs_page(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    access_store = request.app[ACCESS_STORE_KEY]
    page, page_size = _parse_page_params(request)
    q = request.query.get("q")
    chat_raw = request.query.get("chat_id")
    try:
        chat_id = int(chat_raw) if chat_raw else None
    except ValueError:
        chat_id = None
    enabled_raw = request.query.get("enabled")
    bidir_raw = request.query.get("bidirectional")
    enabled = None if enabled_raw is None or enabled_raw == "" else _to_bool(enabled_raw)
    bidirectional = None if bidir_raw is None or bidir_raw == "" else _to_bool(bidir_raw)
    writable_team_ids = access_store.writable_team_ids(request["user"])
    has_writable_teams = writable_team_ids is None or bool(writable_team_ids)
    pair_page = store.page_pairs(
        page=page,
        page_size=page_size,
        name_query=q,
        chat_id=chat_id,
        enabled=enabled,
        bidirectional=bidirectional,
        team_ids=_accessible_team_ids(request),
    )
    return _render_template("pairs.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pairs": pair_page.pairs,
        "pagination": {
            "page": pair_page.page,
            "page_size": pair_page.page_size,
            "total": pair_page.total,
            "pages": pair_page.pages,
        },
        "page_size_options": PAGE_SIZE_OPTIONS,
        "team_names": _team_name_map(request),
        "q": q,
        "chat_id": chat_raw or "",
        "enabled": enabled_raw or "",
        "bidirectional": bidir_raw or "",
        "writable_team_ids": writable_team_ids,
        "has_writable_teams": has_writable_teams,
    })



async def pair_create_page(request: web.Request) -> web.Response:
    teams = request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"])
    if not teams:
        raise web.HTTPForbidden(text="no writable teams")
    return _render_template("pair_form.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pair": None,
        "teams": teams,
        "mask_mappings": [],
        "can_manage_pair": True,
        "error": None,
    })


async def pair_edit_page(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    pair = store.get_pair_by_name(name)
    if pair is None:
        return web.Response(status=404, text="pair not found")
    _assert_pair_visible(request, pair)
    mask_rules = store.list_pair_mask_rules(pair.id) if pair.id is not None else []
    return _render_template("pair_form.html", request, {
        "active_page": "pairs",
        "user": request["user"],
        "pair": pair,
        "teams": request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"]),
        "mask_mappings": _aggregate_pair_masks(mask_rules),
        "can_manage_pair": _can_write_team(request, pair.team_id),
        "error": None,
    })


def _pair_payload_from_form(form) -> dict[str, Any]:
    types_allow = form.getall("types_allow", []) or ["text"]
    return {
        "name": form.get("name"),
        "group_a_chat_id": form.get("group_a_chat_id"),
        "group_b_chat_id": form.get("group_b_chat_id"),
        "bidirectional": _to_bool(form.get("bidirectional"), default=True),
        "enabled": _to_bool(form.get("enabled"), default=False),
        "team_id": form.get("team_id"),
        "filters": {
            "types_allow": list(types_allow),
            "keywords_block": _split_csv(form.get("keywords_block", "")),
            "keywords_allow": _split_csv(form.get("keywords_allow", "")),
        },
    }


async def pair_create_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    form = await request.post()
    payload = _pair_payload_from_form(form)
    if not payload.get("team_id"):
        payload["team_id"] = _first_writable_team_id(request)
    if not _can_write_team(request, int(payload["team_id"]) if payload.get("team_id") else None):
        raise web.HTTPForbidden(text="team not writable")
    payload["created_by_user_id"] = request["user"].id
    try:
        _enforce_bidirectional_policy(payload)
        pair = _pair_from_payload(payload)
        store.create_pair(pair)
    except ValueError as exc:
        return _render_template("pair_form.html", request, {
            "active_page": "pairs",
            "user": request["user"],
            "pair": None,
            "teams": request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"]),
            "mask_mappings": [],
            "can_manage_pair": True,
            "error": str(exc),
        })
    raise web.HTTPFound("/pairs")


async def pair_edit_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    old_name = request.match_info["name"]
    existing = store.get_pair_by_name(old_name)
    if existing is None:
        return web.Response(status=404, text="pair not found")
    _assert_pair_writable(request, existing)
    form = await request.post()
    payload = _pair_payload_from_form(form)
    payload["name"] = old_name
    if not payload.get("team_id"):
        payload["team_id"] = existing.team_id
    if not _can_write_team(request, int(payload["team_id"]) if payload.get("team_id") else None):
        raise web.HTTPForbidden(text="target team not writable")
    payload["created_by_user_id"] = existing.created_by_user_id
    try:
        _enforce_bidirectional_policy(payload, existing_pair=existing)
        updated = _pair_from_payload(payload, pair_id=existing.id)
        store.update_pair(updated)
    except ValueError as exc:
        existing_masks = store.list_pair_mask_rules(existing.id) if existing.id is not None else []
        return _render_template("pair_form.html", request, {
            "active_page": "pairs",
            "user": request["user"],
            "pair": existing,
            "teams": request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"]),
            "mask_mappings": _aggregate_pair_masks(existing_masks),
            "can_manage_pair": True,
            "error": str(exc),
        })
    raise web.HTTPFound("/pairs")


async def pair_delete_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    pair = store.get_pair_by_name(request.match_info["name"])
    if pair is None:
        return web.Response(status=404, text="pair not found")
    _assert_pair_writable(request, pair)
    store.delete_pair(pair.name)
    raise web.HTTPFound("/pairs")


async def pair_mask_create_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    pair = store.get_pair_by_name(request.match_info["name"])
    if pair is None or pair.id is None:
        return web.Response(status=404, text="pair not found")
    _assert_pair_writable(request, pair)
    form = await request.post()
    try:
        telegram_user_id = int(str(form.get("telegram_user_id", "")).strip())
        mode = str(form.get("mode", ""))
        alias = str(form.get("alias", "")).strip() or None
        # Default mask behavior is bidirectional for the same Telegram user.
        for direction in ("a_to_b", "b_to_a"):
            store.upsert_pair_mask_rule(
                PairMaskRule(
                    id=None,
                    pair_id=pair.id,
                    telegram_user_id=telegram_user_id,
                    direction=direction,
                    mode=mode,
                    alias=alias,
                )
            )
    except (TypeError, ValueError) as exc:
        pair_masks = store.list_pair_mask_rules(pair.id)
        return _render_template("pair_form.html", request, {
            "active_page": "pairs",
            "user": request["user"],
            "pair": pair,
            "teams": request.app[ACCESS_STORE_KEY].list_writable_teams(request["user"]),
            "mask_mappings": _aggregate_pair_masks(pair_masks),
            "can_manage_pair": True,
            "error": str(exc),
        })
    raise web.HTTPFound(f"/pairs/{pair.name}/edit")


async def pair_mask_delete_submit(request: web.Request) -> web.StreamResponse:
    store = request.app[CONFIG_STORE_KEY]
    pair = store.get_pair_by_name(request.match_info["name"])
    if pair is None or pair.id is None:
        return web.Response(status=404, text="pair not found")
    _assert_pair_writable(request, pair)
    telegram_user_id = int(request.match_info["telegram_user_id"])
    rules = [
        row for row in store.list_pair_mask_rules(pair.id)
        if row.telegram_user_id == telegram_user_id
    ]
    if not rules:
        return web.Response(status=404, text="mask rule not found")
    for rule in rules:
        store.delete_pair_mask_rule_for_pair(pair_id=pair.id, rule_id=rule.id)
    raise web.HTTPFound(f"/pairs/{pair.name}/edit")


async def api_list_pairs(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    page, page_size = _parse_page_params(request)
    q = request.query.get("q")
    chat_raw = request.query.get("chat_id")
    try:
        chat_id = int(chat_raw) if chat_raw else None
    except ValueError:
        chat_id = None
    enabled_raw = request.query.get("enabled")
    bidir_raw = request.query.get("bidirectional")
    enabled = None if enabled_raw is None else _to_bool(enabled_raw)
    bidirectional = None if bidir_raw is None else _to_bool(bidir_raw)
    pair_page = store.page_pairs(
        page=page,
        page_size=page_size,
        name_query=q,
        chat_id=chat_id,
        enabled=enabled,
        bidirectional=bidirectional,
        team_ids=_accessible_team_ids(request),
    )
    return web.json_response({
        "pairs": [_json_pair(row) for row in pair_page.pairs],
        "pagination": {
            "page": pair_page.page,
            "page_size": pair_page.page_size,
            "total": pair_page.total,
            "pages": pair_page.pages,
        },
    })


async def api_create_pair(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    payload = await request.json()
    if not payload.get("team_id"):
        payload["team_id"] = _first_writable_team_id(request)
    if not _can_write_team(request, int(payload["team_id"]) if payload.get("team_id") else None):
        raise web.HTTPForbidden(text="team not writable")
    payload["created_by_user_id"] = request["user"].id
    try:
        _enforce_bidirectional_policy(payload)
        pair = _pair_from_payload(payload)
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
    _assert_pair_writable(request, existing)
    payload = await request.json()
    payload["name"] = payload.get("name", existing.name)
    payload["team_id"] = payload.get("team_id", existing.team_id)
    payload["created_by_user_id"] = existing.created_by_user_id
    if not _can_write_team(request, int(payload["team_id"]) if payload.get("team_id") else None):
        raise web.HTTPForbidden(text="target team not writable")
    try:
        _enforce_bidirectional_policy(payload, existing_pair=existing)
        updated = _pair_from_payload(payload, pair_id=existing.id)
        store.update_pair(updated)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({"pair": _json_pair(updated)})


async def api_delete_pair(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    name = request.match_info["name"]
    pair = store.get_pair_by_name(name)
    if pair is None:
        return web.json_response({"error": "pair_not_found"}, status=404)
    _assert_pair_writable(request, pair)
    store.delete_pair(name)
    return web.json_response({"ok": True})


async def api_alias_suggestions(request: web.Request) -> web.Response:
    store = request.app[CONFIG_STORE_KEY]
    try:
        telegram_user_id = int(request.query.get("telegram_user_id", ""))
    except ValueError:
        return web.json_response({"aliases": []})
    aliases = store.suggest_aliases(
        telegram_user_id=telegram_user_id,
        team_ids=_accessible_team_ids(request),
    )
    return web.json_response({"aliases": aliases})


async def api_backup_now(request: web.Request) -> web.Response:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="backups not allowed")
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


async def api_stats(request: web.Request) -> web.Response:
    stats_path = request.app[STATS_PATH_KEY]
    try:
        with open(stats_path) as f:
            raw: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}

    today = sum(v.get("today", 0) for v in raw.values())
    week = sum(v.get("week", 0) for v in raw.values())

    store = request.app[CONFIG_STORE_KEY]
    pairs = store.list_pairs(team_ids=_accessible_team_ids(request))
    pairs_total = len(pairs)
    pairs_active = sum(1 for p in pairs if p.enabled)

    return web.json_response({
        "today": today,
        "week": week,
        "pairs_total": pairs_total,
        "pairs_active": pairs_active,
    })


async def users_page(request: web.Request) -> web.Response:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="users not allowed")
    return _render_users_page(request, error=None)


def _render_users_page(request: web.Request, *, error: str | None) -> web.Response:
    auth_store = request.app[AUTH_STORE_KEY]
    return _render_template("users.html", request, {
        "active_page": "users",
        "user": request["user"],
        "users": auth_store.list_users(),
        "can_grant_super_admin": _can_grant_super_admin(request),
        "error": error,
    })


async def user_create_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="users not allowed")
    auth_store = request.app[AUTH_STORE_KEY]
    form = await request.post()
    target_role = str(form.get("global_role", "user"))
    if target_role == "super_admin" and not _can_grant_super_admin(request):
        raise web.HTTPForbidden(text="super admin grant not allowed")
    try:
        auth_store.create_user(
            username=str(form.get("username", "")),
            password=str(form.get("password", "")),
            global_role=target_role,
            is_active=_to_bool(form.get("is_active"), default=False),
        )
    except ValueError as exc:
        return _render_users_page(request, error=str(exc))
    raise web.HTTPFound("/users")


async def user_update_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="users not allowed")
    auth_store = request.app[AUTH_STORE_KEY]
    user_id = int(request.match_info["user_id"])
    target = auth_store.get_user_by_id(user_id)
    if target is None:
        return _render_users_page(request, error="user not found")

    form = await request.post()
    password = str(form.get("password", ""))
    global_role = str(form.get("global_role", "user"))
    is_active = _to_bool(form.get("is_active"), default=False)

    if global_role == "super_admin" and not _can_grant_super_admin(request):
        raise web.HTTPForbidden(text="super admin grant not allowed")
    if target.global_role == "super_admin" and not _can_grant_super_admin(request):
        raise web.HTTPForbidden(text="super admin update not allowed")
    if request["user"].id == user_id and not is_active:
        return _render_users_page(request, error="cannot deactivate your own account")

    active_super_admins = auth_store.count_active_super_admins()
    target_is_active_super_admin = target.global_role == "super_admin" and target.is_active
    will_remain_active_super_admin = global_role == "super_admin" and is_active
    if (
        target_is_active_super_admin
        and not will_remain_active_super_admin
        and active_super_admins <= 1
    ):
        return _render_users_page(request, error="cannot remove the last active super_admin")

    try:
        auth_store.update_user(
            user_id,
            global_role=global_role,
            is_active=is_active,
            password=password or None,
        )
    except ValueError as exc:
        return _render_users_page(request, error=str(exc))
    raise web.HTTPFound("/users")


async def user_delete_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="users not allowed")
    auth_store = request.app[AUTH_STORE_KEY]
    user_id = int(request.match_info["user_id"])
    target = auth_store.get_user_by_id(user_id)
    if target is None:
        return _render_users_page(request, error="user not found")
    if user_id == request["user"].id:
        return _render_users_page(request, error="cannot delete your own account")
    if target.global_role == "super_admin" and not _can_grant_super_admin(request):
        raise web.HTTPForbidden(text="super admin delete not allowed")
    if target.global_role == "super_admin" and target.is_active:
        if auth_store.count_active_super_admins() <= 1:
            return _render_users_page(request, error="cannot delete the last active super_admin")
    auth_store.delete_user(user_id)
    raise web.HTTPFound("/users")


async def teams_page(request: web.Request) -> web.Response:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    return _render_teams_page(request, error=None)


def _render_teams_page(
    request: web.Request,
    *,
    error: str | None,
    selected_team_id: int | None = None,
) -> web.Response:
    access_store = request.app[ACCESS_STORE_KEY]
    teams = access_store.list_teams()
    resolved_selected_team_id = selected_team_id
    if resolved_selected_team_id is None:
        resolved_selected_team_id = teams[0].id if teams else 0
        selected_raw = request.query.get("team_id")
        if selected_raw:
            try:
                resolved_selected_team_id = int(selected_raw)
            except ValueError:
                resolved_selected_team_id = teams[0].id if teams else 0
    selected_team = (
        access_store.get_team(resolved_selected_team_id) if resolved_selected_team_id else None
    )
    default_team_id = next((team.id for team in teams if team.name == "Default"), None)
    selected_team_has_pairs = False
    if selected_team is not None:
        selected_team_has_pairs = bool(
            request.app[CONFIG_STORE_KEY].list_pairs(team_ids=[selected_team.id])
        )
    return _render_template("teams.html", request, {
        "active_page": "teams",
        "user": request["user"],
        "teams": teams,
        "default_team_id": default_team_id,
        "selected_team": selected_team,
        "selected_team_has_pairs": selected_team_has_pairs,
        "members": access_store.list_team_members(selected_team.id) if selected_team else [],
        "users": request.app[AUTH_STORE_KEY].list_users(),
        "error": error,
    })


async def team_create_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    form = await request.post()
    try:
        team = request.app[ACCESS_STORE_KEY].create_team(str(form.get("name", "")))
    except ValueError as exc:
        return _render_teams_page(request, error=str(exc))
    raise web.HTTPFound(f"/teams?team_id={team.id}")


async def team_member_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    form = await request.post()
    team_id = int(request.match_info["team_id"])
    try:
        request.app[ACCESS_STORE_KEY].upsert_team_member(
            team_id=team_id,
            user_id=int(str(form.get("user_id", ""))),
            role=str(form.get("role", "viewer")),
        )
    except (TypeError, ValueError) as exc:
        return _render_teams_page(request, error=str(exc), selected_team_id=team_id)
    raise web.HTTPFound(f"/teams?team_id={team_id}")


async def team_member_delete_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    team_id = int(request.match_info["team_id"])
    request.app[ACCESS_STORE_KEY].remove_team_member(
        team_id=team_id,
        user_id=int(request.match_info["user_id"]),
    )
    raise web.HTTPFound(f"/teams?team_id={team_id}")


async def team_update_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    access_store = request.app[ACCESS_STORE_KEY]
    team_id = int(request.match_info["team_id"])
    team = access_store.get_team(team_id)
    if team is None:
        return _render_teams_page(request, error="team not found")
    if team.name == "Default":
        return _render_teams_page(request, error="Default team cannot be renamed")
    form = await request.post()
    try:
        updated = access_store.update_team(team_id=team_id, name=str(form.get("name", "")))
    except ValueError as exc:
        return _render_teams_page(request, error=str(exc))
    raise web.HTTPFound(f"/teams?team_id={updated.id}")


async def team_delete_submit(request: web.Request) -> web.StreamResponse:
    if not _can_manage_admin_area(request):
        raise web.HTTPForbidden(text="teams not allowed")
    access_store = request.app[ACCESS_STORE_KEY]
    team_id = int(request.match_info["team_id"])
    team = access_store.get_team(team_id)
    if team is None:
        return _render_teams_page(request, error="team not found")
    if team.name == "Default":
        return _render_teams_page(request, error="Default team cannot be deleted")
    if request.app[CONFIG_STORE_KEY].list_pairs(team_ids=[team_id]):
        return _render_teams_page(request, error="Cannot delete team with assigned pairs")
    try:
        access_store.delete_team(team_id)
    except ValueError as exc:
        return _render_teams_page(request, error=str(exc))
    teams = access_store.list_teams()
    if not teams:
        raise web.HTTPFound("/teams")
    raise web.HTTPFound(f"/teams?team_id={teams[0].id}")


def create_admin_app(
    *,
    db_path: str,
    config_store: SQLiteConfigStore,
    auth_store: AuthStore,
    backup_dir: str = "backups",
    backup_retention_days: int = 30,
    stats_path: str = "data/stats.json",
) -> web.Application:
    app = web.Application(middlewares=[ui_preferences_middleware, auth_middleware])
    app[DB_PATH_KEY] = db_path
    app[CONFIG_STORE_KEY] = config_store
    app[AUTH_STORE_KEY] = auth_store
    app[ACCESS_STORE_KEY] = AccessStore(db_path)
    app[BACKUP_DIR_KEY] = backup_dir
    app[BACKUP_RETENTION_DAYS_KEY] = backup_retention_days
    app[STATS_PATH_KEY] = stats_path

    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
    )

    app.router.add_static("/static/", path=str(Path(__file__).parent / "static"), name="static")
    app.router.add_get("/", index_handler)
    app.router.add_get("/dashboard", dashboard_page)
    app.router.add_get("/backups", backups_page)
    app.router.add_get("/users", users_page)
    app.router.add_post("/users", user_create_submit)
    app.router.add_post("/users/{user_id}/edit", user_update_submit)
    app.router.add_post("/users/{user_id}/delete", user_delete_submit)
    app.router.add_get("/teams", teams_page)
    app.router.add_post("/teams", team_create_submit)
    app.router.add_post("/teams/{team_id}/edit", team_update_submit)
    app.router.add_post("/teams/{team_id}/delete", team_delete_submit)
    app.router.add_post("/teams/{team_id}/members", team_member_submit)
    app.router.add_post("/teams/{team_id}/members/{user_id}/delete", team_member_delete_submit)
    app.router.add_get("/login", login_page)
    app.router.add_post("/login", post_login)
    app.router.add_post("/api/login", api_login)
    app.router.add_post("/api/logout", api_logout)
    app.router.add_get("/pairs", pairs_page)
    app.router.add_get("/pairs/new", pair_create_page)
    app.router.add_post("/pairs/new", pair_create_submit)
    app.router.add_get("/pairs/{name}/edit", pair_edit_page)
    app.router.add_post("/pairs/{name}/edit", pair_edit_submit)
    app.router.add_post("/pairs/{name}/delete", pair_delete_submit)
    app.router.add_post("/pairs/{name}/masks", pair_mask_create_submit)
    app.router.add_post("/pairs/{name}/masks/{telegram_user_id}/delete", pair_mask_delete_submit)
    app.router.add_get("/api/pairs", api_list_pairs)
    app.router.add_post("/api/pairs", api_create_pair)
    app.router.add_put("/api/pairs/{name}", api_update_pair)
    app.router.add_delete("/api/pairs/{name}", api_delete_pair)
    app.router.add_get("/api/mask-aliases", api_alias_suggestions)
    app.router.add_post("/api/backup", api_backup_now)
    app.router.add_get("/api/stats", api_stats)
    return app
