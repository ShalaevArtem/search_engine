import pytest
from datetime import datetime
from whoosh import index
from core.searcher import setup_search_parser, search_index, search_time_range, search_by_filename
from models.schemas import search_schema


@pytest.fixture
def temp_index(tmp_path):
    """Создаёт временный индекс с 2 документами: один для admin, один для user+admin."""
    ix_dir = tmp_path / "idx"
    ix_dir.mkdir()
    ix = index.create_in(ix_dir, schema=search_schema)

    writer = ix.writer()

    # Документ ТОЛЬКО для admin
    writer.add_document(
        path=str(tmp_path / "admin_secret.txt"),
        filename="admin_secret.txt",
        content="секретный отчёт о финансах компании",
        last_modified=datetime.now(),
        roles="admin"
    )

    # Документ для user и admin
    writer.add_document(
        path=str(tmp_path / "user_public.txt"),
        filename="user_public.txt",
        content="публичный отчёт о проекте",
        last_modified=datetime.now(),
        roles="user,admin"
    )

    writer.commit()
    return ix


def test_user_cannot_find_admin_document_by_keywords(temp_index):
    """User видит только свои документы при поиске по ключевым словам."""
    parser = setup_search_parser(temp_index.schema)
    with temp_index.searcher() as searcher:
        results = search_index(searcher, parser, "отчёт", user_roles=["user"])
        assert len(results) == 1
        assert results[0]["path"].endswith("user_public.txt")


def test_user_cannot_find_admin_document_by_date(temp_index):
    """User видит только свои документы при поиске по дате."""
    with temp_index.searcher() as searcher:
        today = datetime.now().strftime("%Y-%m-%d")
        results = search_time_range(searcher, today, today, user_roles=["user"])
        assert len(results) == 1
        assert results[0]["path"].endswith("user_public.txt")


def test_user_cannot_find_admin_document_by_filename(temp_index):
    """User не находит файл admin при поиске по имени."""
    with temp_index.searcher() as searcher:
        results = search_by_filename(searcher, "admin_secret", user_roles=["user"])
        assert len(results) == 0


def test_admin_can_find_all_documents(temp_index):
    """Admin видит все документы."""
    parser = setup_search_parser(temp_index.schema)
    with temp_index.searcher() as searcher:
        results = search_index(searcher, parser, "отчёт", user_roles=["admin"])
        assert len(results) == 2