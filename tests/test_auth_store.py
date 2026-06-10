from bot.storage.auth_store import AuthStore, hash_password, verify_password
from bot.storage.sqlite_db import initialize_database


def test_password_hash_roundtrip():
    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_auth_store_user_and_session_flow(tmp_path):
    db_path = str(tmp_path / "forwarder.db")
    initialize_database(db_path)
    store = AuthStore(db_path)
    store.ensure_admin_user("admin", "secret")

    user = store.get_user_by_username("admin")
    assert user is not None
    assert user.username == "admin"

    session_id = store.create_session(user.id, ttl_hours=1)
    from_session = store.get_user_by_session(session_id)
    assert from_session is not None
    assert from_session.username == "admin"

    store.delete_session(session_id)
    assert store.get_user_by_session(session_id) is None
