import fnmatch
from pathlib import Path
import logging
from models.database import SessionLocal, DocumentACL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_cached_acl = None

def _load_acl_rules():
    db = SessionLocal()
    try:
        rules = db.query(DocumentACL).all()
        processed = []
        for rule in rules:
            # Преобразуем маску в объект Path для безопасного сравнения
            p_mask = Path(rule.path_mask).resolve()
            processed.append({
                "path": p_mask,
                "roles": rule.allowed_roles.split(','),
                "is_recursive": getattr(rule, 'is_recursive', False)
            })
        return processed
    finally:
        db.close()

def get_acl_rules():
    global _cached_acl
    if _cached_acl is None:
        _cached_acl = _load_acl_rules()
    return _cached_acl

def check_file_access(file_path: str, roles: list[str]) -> bool:
    """Безопасная проверка прав с защитой от Path Traversal"""
    if not roles: return False
    if "admin" in roles: return True

    try:
        p_file = Path(file_path).resolve()
    except Exception:
        return False

    for rule in get_acl_rules():
        if not any(role in rule["roles"] for role in roles):
            continue

        p_mask = rule["path"]

        if rule["is_recursive"]:
            # is_relative_to безопасно проверяет вложенность, исключая ../
            if p_file.is_relative_to(p_mask):
                return True
        else:
            # Для файлов используем fnmatch, но только после нормализации пути
            # Преобразуем Path обратно в строку для fnmatch
            if fnmatch.fnmatch(str(p_file), str(p_mask)):
                return True
    return False

def filter_results_by_access(results: list, roles: list[str]) -> list:
    if not roles: return []
    return [r for r in results if check_file_access(r.get("path", ""), roles)]