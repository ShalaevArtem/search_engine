from core.auth_manager import hash_password, verify_password


def test_hash_and_verify_success():
    """Хеширование и корректная проверка пароля."""
    pwd = "MySecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert "$" in hashed  # формат: salt$hash
    assert verify_password(pwd, hashed) is True


def test_verify_wrong_password():
    """Неверный пароль не проходит проверку."""
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_verify_malformed_hash():
    """Защита от некорректного хеша (не падает, возвращает False)."""
    assert verify_password("test", "badhash") is False
    assert verify_password("test", "") is False
    assert verify_password("test", "no_dollar_sign") is False