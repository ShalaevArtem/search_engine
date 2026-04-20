from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy import func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "secure_search.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Таблица связи многие-ко-многим (user <-> role)
user_roles = Table(
    'user_roles', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('role_id', Integer, ForeignKey('roles.id'))
)

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    user = relationship("User", back_populates="sessions")

class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, default="")
    users = relationship("User", secondary=user_roles, back_populates="roles")


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Создаёт таблицы и добавляет дефолтные роли/админа/правила доступа."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Создаём админа, если БД пуста (ИЗМЕНИТЬ ОПРЕДЕЛЕНИЕ АДМИНА)
        if db.query(User).first() is None:
            from core.auth_manager import hash_password
            pwd_hash = hash_password("admin123")
            admin_role = Role(name="admin", description="Полный доступ")
            user_role = Role(name="user", description="Стандартный доступ")
            admin_user = User(username="admin", password_hash=pwd_hash, is_active=True)
            admin_user.roles.append(admin_role)
            db.add_all([admin_role, user_role, admin_user])

        # 2. Создаём правила доступа (ACL), если таблица пуста
        if db.query(DocumentACL).first() is None:
            db.add_all([
                # Админ имеет доступ ко всему
                DocumentACL(path_mask="*", allowed_roles="admin"),
                # Пользователь видит только файлы из D:\Test\ и любые .txt
                DocumentACL(path_mask="D:\\Test\\*", allowed_roles="admin,user"),
                DocumentACL(path_mask="*.txt", allowed_roles="admin,user"),
            ])
        db.commit()
    finally:
        db.close()

class DocumentACL(Base):
    __tablename__ = 'document_acl'
    id = Column(Integer, primary_key=True, index=True)
    path_mask = Column(String, unique=True, index=True)
    allowed_roles = Column(String, nullable=False)
    is_recursive = Column(Boolean, default=False)