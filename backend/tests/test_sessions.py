from app.sessions import create_session, get_user_id_for_token


def test_valid_token_resolves_to_user():
    token = create_session(user_id=42)
    assert get_user_id_for_token(token) == 42


def test_unknown_token_returns_none():
    assert get_user_id_for_token("not-a-real-token") is None


def test_empty_token_returns_none():
    assert get_user_id_for_token("") is None
    assert get_user_id_for_token(None) is None


def test_tokens_are_unique_per_call():
    t1 = create_session(user_id=1)
    t2 = create_session(user_id=1)
    assert t1 != t2
