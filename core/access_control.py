import fnmatch
import os
import logging
from models.database import SessionLocal, DocumentACL

logger = logging.getLogger(__name__)
_cached_acl = None
def invalidate_acl_cache():
    """Сбрасывает кэш ACL. Вызывается после любого изменения прав в БД."""
    global _cached_acl
    _cached_acl = None

def _normalize_path(p: str) -> str:
    """Приводит путь к единому формату: нижний регистр, обратные слеши, без конечных слешей."""
    if not p:
        return ""
    p = os.path.normcase(os.path.normpath(p))
    p = p.replace("/", "\\")
    return p.rstrip("\\")

def _load_acl_rules():
    db = SessionLocal()
    try:
        rules = db.query(DocumentACL).all()
        processed = []
        for rule in rules:
            raw_mask = rule.path_mask
            is_recursive = getattr(rule, "is_recursive", False)
            roles = [r.strip() for r in rule.allowed_roles.split(",") if r.strip()]

            # Для рекурсивных правил убираем wildcard, оставляем только базовую директорию
            base_mask = raw_mask.replace("*", "").replace("?", "")
            base_mask = _normalize_path(base_mask)

            # Для точных масок сохраняем wildcard
            full_mask = _normalize_path(raw_mask)

            processed.append({
                "base_dir": base_mask,
                "full_mask": full_mask,
                "roles": roles,
                "is_recursive": is_recursive
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
    """Проверяет права на файл с учётом регистронезависимости и рекурсии."""
    if not roles:
        return False
    if "admin" in roles:
        return True

    norm_file = _normalize_path(file_path)

    for rule in get_acl_rules():
        if not any(role in rule["roles"] for role in roles):
            continue

        if rule["is_recursive"]:
            # Рекурсивный доступ: файл должен находиться внутри базовой директории
            # Добавляем разделитель, чтобы 'd:\docs' не совпадал с 'd:\documents'
            if norm_file.startswith(rule["base_dir"] + "\\"):
                return True
            # На случай, если путь совпадает с самой директорией
            if norm_file == rule["base_dir"]:
                return True
        else:
            # Точное совпадение по маске (поддерживает * и ?)
            if fnmatch.fnmatch(norm_file, rule["full_mask"]):
                return True
    return False

def filter_results_by_access(results: list, roles: list[str]) -> list:
    """Фильтрует результаты поиска, оставляя только доступные файлы."""
    if not roles:
        return []
    return [r for r in results if check_file_access(r.get("path", ""), roles)]

def get_allowed_roles_for_path(file_path: str) -> list[str]:
    """
    Возвращает список ролей, которые имеют доступ к файлу.
    Используется при индексации для записи поля 'roles' в индекс.
    """
    try:
        norm_file = _normalize_path(file_path)
    except Exception:
        return []

    allowed = set()
    for rule in get_acl_rules():
        if rule["is_recursive"]:
            base_dir = rule["base_dir"] + "\\"
            if norm_file.startswith(base_dir) or norm_file == rule["base_dir"]:
                allowed.update(rule["roles"])
        else:
            if fnmatch.fnmatch(norm_file, rule["full_mask"]):
                allowed.update(rule["roles"])
    return list(allowed)
