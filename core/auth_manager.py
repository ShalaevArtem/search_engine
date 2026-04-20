import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from models.database import SessionLocal, User, Role, init_db, Session
from secrets import token_urlsafe
from datetime import datetime, timedelta, timezone

SESSION_FILE = Path(__file__).parent.parent / "session.token"

@dataclass
class CurrentUser:
    id: int
    username: str
    roles: list[str]

def hash_password(password: str) -> str:
    """Хеширование пароля через PBKDF2-HMAC-SHA256 (встроенный в Python)."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Проверка пароля."""
    try:
        salt, pwd_hash = stored_hash.split("$")
        pwd_hash_calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return pwd_hash_calc.hex() == pwd_hash
    except Exception:
        return False

class AuthManager:
    _instance = None
    _current_user: Optional[CurrentUser] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            init_db()  # БД инициализируется один раз при первом обращении
        return cls._instance

    def authenticate(self, username: str, password: str) -> bool:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username, User.is_active == True).first()
            if not user:
                return False
            if verify_password(password, user.password_hash):
                roles = [role.name for role in user.roles]
                self._current_user = CurrentUser(id=user.id, username=user.username, roles=roles)
                return True
            return False
        finally:
            db.close()

    def get_current_user(self) -> Optional[CurrentUser]:
        return self._current_user

    def logout(self):
        self._current_user = None

    def has_role(self, role_name: str) -> bool:
        if not self._current_user:
            return False
        return role_name in self._current_user.roles

    def create_session_token(self, username: str, password: str, remember: bool = False) -> str | None:
        if not self.authenticate(username, password):
            return None

        token = secrets.token_urlsafe(32)
        # 30 дней если "запомнить", иначе 24 часа
        expires = datetime.now(timezone.utc) + timedelta(days=30 if remember else 1)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            # Чистим старые сессии
            db.query(Session).filter(Session.user_id == user.id).delete()
            db.add(Session(token=token, user_id=user.id, expires_at=expires))
            db.commit()
        finally:
            db.close()

        SESSION_FILE.write_text(token, encoding="utf-8")
        print(f"[Auth] Сессия создана: {username} | expires: {expires}")
        return token

    def check_stored_session(self) -> bool:
        try:
            if not SESSION_FILE.exists(): return False
            token = SESSION_FILE.read_text(encoding="utf-8").strip()
            if not token: return False

            db = SessionLocal()
            try:
                sess = db.query(Session).filter(Session.token == token).first()
                if not sess:
                    SESSION_FILE.unlink(missing_ok=True)
                    return False

                now_utc = datetime.now(timezone.utc)
                expires_at = sess.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                if expires_at < now_utc:
                    db.query(Session).filter(Session.token == token).delete()
                    db.commit()
                    SESSION_FILE.unlink(missing_ok=True)
                    print("[Auth] Токен истёк") #TEST: УДАЛИТЬ
                    return False

                user = sess.user
                if not user or not user.is_active:
                    print("[Auth] Пользователь заблокирован") #TEST: УДАЛИТЬ
                    return False

                self._current_user = CurrentUser(
                    id=user.id, username=user.username, roles=[r.name for r in user.roles]
                )
                print(f"[Auth] Автовход: {user.username}") #TEST: УДАЛИТЬ
                return True
            finally:
                db.close()
        except Exception as e:
            print(f"[Auth] Ошибка проверки сессии: {e}") #TEST: УДАЛИТЬ
            return False

    def clear_session(self):
        self._current_user = None
        if SESSION_FILE.exists():
            SESSION_FILE.unlink(missing_ok=True)

auth_manager = AuthManager()
