from app.security import hash_password, verify_password


def test_correct_password_verifies():
    stored = hash_password("MyPassw0rd!")
    assert verify_password("MyPassw0rd!", stored) is True


def test_wrong_password_fails():
    stored = hash_password("MyPassw0rd!")
    assert verify_password("wrongpassword", stored) is False


def test_hash_is_salted_and_not_plaintext():
    stored = hash_password("MyPassw0rd!")
    assert "MyPassw0rd!" not in stored
    assert ":" in stored
