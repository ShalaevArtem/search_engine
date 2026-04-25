from unittest.mock import patch
from core.access_control import get_acl_rules, invalidate_acl_cache


def test_acl_cache_invalidation():
    """Кэш ACL сбрасывается только после явного вызова invalidate_acl_cache()."""
    call_count = 0

    def fake_load():
        nonlocal call_count
        call_count += 1
        return [{"base_dir": "C:\\test", "roles": ["admin"], "is_recursive": True}]

    with patch("core.access_control._load_acl_rules", side_effect=fake_load):
        # Первый вызов — читает из БД
        invalidate_acl_cache()
        rules1 = get_acl_rules()
        assert call_count == 1

        # Второй вызов — берёт из кэша, БД не трогает
        rules2 = get_acl_rules()
        assert call_count == 1
        assert rules1 is rules2  # тот же объект в памяти

        # Инвалидация — следующий вызов снова читает из БД
        invalidate_acl_cache()
        rules3 = get_acl_rules()
        assert call_count == 2