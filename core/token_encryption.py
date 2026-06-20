"""Модуль шифрования токена сессии."""

import logging
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

SERVICE_NAME = "SecureSearchApp"
KEY_NAME = "session_token_encryption_key"

KEY_FILE = Path(__file__).parent.parent / ".token_key"

def _get_or_create_key() -> bytes:
    """
    Получает ключ шифрования из Credential Manager или создаёт новый.
    Returns:
        bytes: Ключ шифрования Fernet (32 байта, base64-кодированные)
    """
    try:
        import keyring
        key_b64 = keyring.get_password(SERVICE_NAME, KEY_NAME)
        if key_b64:
            logger.debug("Ключ шифрования загружен из Credential Manager")
            return key_b64.encode('utf-8')
    except Exception as e:
        logger.warning(f"Credential Manager недоступен: {e}")

    if KEY_FILE.exists():
        try:
            key_b64 = KEY_FILE.read_text(encoding='utf-8').strip()
            if key_b64:
                logger.info("Ключ шифрования загружен из файла (fallback)")
                return key_b64.encode('utf-8')
        except Exception as e:
            logger.warning(f"Не удалось прочитать файл ключа: {e}")

    logger.info("Генерация нового ключа шифрования")
    new_key = Fernet.generate_key()

    try:
        import keyring
        keyring.set_password(SERVICE_NAME, KEY_NAME, new_key.decode('utf-8'))
        logger.info("Ключ сохранён в Credential Manager")
        return new_key
    except Exception as e:
        logger.warning(f"Не удалось сохранить ключ в Credential Manager: {e}")

    try:
        KEY_FILE.write_text(new_key.decode('utf-8'), encoding='utf-8')
        KEY_FILE.chmod(0o600)
        logger.warning("Ключ сохранён в файл (fallback). Рекомендуется использовать Credential Manager.")
        return new_key
    except Exception as e:
        logger.error(f"Не удалось сохранить ключ шифрования: {e}")
        raise RuntimeError("Невозможно создать или сохранить ключ шифрования")

def encrypt_token(token: str) -> str:
    """
    Шифрует токен сессии.
    Args:
        token: Токен сессии (строка)
    Returns:
        str: Зашифрованный токен (base64-строка)
    """
    if not token:
        raise ValueError("Токен не может быть пустым")

    key = _get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(token.encode('utf-8'))
    return encrypted.decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """
    Расшифровывает токен сессии.
    Args:
        encrypted_token: Зашифрованный токен (base64-строка)
    Returns:
        str: Исходный токен сессии
    Raises:
        cryptography.fernet.InvalidToken: Если токен повреждён или ключ неверный
    """
    if not encrypted_token:
        raise ValueError("Зашифрованный токен не может быть пустым")

    key = _get_or_create_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted_token.encode('utf-8'))
    return decrypted.decode('utf-8')

def reset_encryption_key():
    """
    Сбрасывает ключ шифрования (для тестирования).
    Удаляет ключ из Credential Manager и файла.
    """
    logger.warning("Сброс ключа шифрования")

    try:
        import keyring
        keyring.delete_password(SERVICE_NAME, KEY_NAME)
        logger.info("Ключ удалён из Credential Manager")
    except Exception as e:
        logger.debug(f"Не удалось удалить ключ из Credential Manager: {e}")

    if KEY_FILE.exists():
        try:
            KEY_FILE.unlink()
            logger.info("Файл ключа удалён")
        except Exception as e:
            logger.error(f"Не удалось удалить файл ключа: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_token = "test_session_token_12345"
    encrypted = encrypt_token(test_token)
    decrypted = decrypt_token(encrypted)
    assert test_token == decrypted