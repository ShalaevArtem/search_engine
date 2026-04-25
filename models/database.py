import logging
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy import func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, configure_mappers
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "secure_search.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 10, "check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

logger = logging.getLogger(__name__)

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

configure_mappers()

class DocumentACL(Base):
    __tablename__ = 'document_acl'
    id = Column(Integer, primary_key=True, index=True)
    path_mask = Column(String, unique=True, index=True)
    allowed_roles = Column(String, nullable=False)
    is_recursive = Column(Boolean, default=False)

def init_db() -> bool:
    """Создаёт таблицы и дефолтные ACL. Возвращает True, если система уже настроена (есть пользователи)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Инициализируем правила доступа, если таблица пуста
        if db.query(DocumentACL).first() is None:
            db.add_all([
                DocumentACL(path_mask="*", allowed_roles="admin", is_recursive=True),
                DocumentACL(path_mask="D:\\Test\\*", allowed_roles="admin,user", is_recursive=True),
                DocumentACL(path_mask="*.txt", allowed_roles="admin,user", is_recursive=False),
            ])
            db.commit()

        # 2. Проверяем, есть ли уже пользователи
        user_count = db.query(User).count()
        return user_count > 0
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        db.rollback()
        return False
    finally:
        db.close()