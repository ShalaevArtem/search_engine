import fnmatch
from models.database import SessionLocal, DocumentACL

_cached_acl = None


def _load_acl_rules():
    """Загружает правила ACL из БД. Возвращает список кортежей: (маска, список_ролей, is_recursive)."""
    db = SessionLocal()
    try:
        rules = db.query(DocumentACL).all()
        return [
            (
                rule.path_mask.lower().replace('\\', '/'),
                rule.allowed_roles.split(','),
                bool(getattr(rule, 'is_recursive', False))
            )
            for rule in rules
        ]
    finally:
        db.close()


def get_acl_rules():
    """Возвращает кэшированные правила. Загружает из БД только один раз за сессию."""
    global _cached_acl
    if _cached_acl is None:
        _cached_acl = _load_acl_rules()
    return _cached_acl


def check_file_access(file_path: str, roles: list[str]) -> bool:
    """Проверяет, есть ли у пользователя права на файл."""
    if not roles:
        return False
    if "admin" in roles:
        return True

    path_norm = file_path.lower().replace('\\', '/')

    for mask, allowed_roles, is_recursive in get_acl_rules():
        # Проверяем, разрешено ли правило хотя бы для одной роли пользователя
        if not any(role in allowed_roles for role in roles):
            continue

        if is_recursive:
            # Рекурсивное правило: путь должен начинаться с базовой директории
            base_dir = mask.rstrip('*').rstrip('/') + '/'
            if path_norm.startswith(base_dir):
                return True
        else:
            # Точное совпадение по маске (fnmatch поддерживает * и ?)
            if fnmatch.fnmatch(path_norm, mask):
                return True
    return False


def filter_results_by_access(results: list, roles: list[str]) -> list:
    """Фильтрует результаты поиска, оставляя только доступные файлы."""
    if not roles:
        return []
    return [r for r in results if check_file_access(r.get("path", ""), roles)]