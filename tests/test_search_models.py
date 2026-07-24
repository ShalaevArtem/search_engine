import pytest
from datetime import datetime
from unittest.mock import patch
from whoosh import index

from core.searcher import search_time_range, combined_search, search_index
from models.schemas import search_schema

@pytest.fixture
def temp_index(tmp_path):
    """Индекс с документами за разные даты."""
    ix_dir = tmp_path / "idx"
    ix_dir.mkdir()
    ix = index.create_in(ix_dir, schema=search_schema)

    writer = ix.writer()

    writer.add_document(
        path=str(tmp_path / "jan_doc.txt"),
        filename="jan_doc.txt",
        content="отчёт за январь",
        last_modified=datetime(2026, 1, 15, 10, 0, 0),
        roles="admin,user"
    )

    writer.add_document(
        path=str(tmp_path / "mar_doc.txt"),
        filename="mar_doc.txt",
        content="отчёт за март",
        last_modified=datetime(2026, 3, 20, 10, 0, 0),
        roles="admin,user"
    )

    writer.commit()
    return ix

def test_search_by_date_only(temp_index):
    """Поиск только по дате (пустой текст, включена дата)."""
    with temp_index.searcher() as searcher:
        results = search_time_range(
            searcher,
            "2026-01-01",  # start
            "2026-01-31",  # end
            user_roles=["user"],
            limit=10
        )
        assert len(results) == 1
        assert results[0]["path"].endswith("jan_doc.txt")

def test_search_by_date_no_results(temp_index):
    """Поиск по дате, где ничего нет."""
    with temp_index.searcher() as searcher:
        results = search_time_range(
            searcher,
            "2025-01-01",
            "2025-01-31",
            user_roles=["user"],
            limit=10
        )
        assert len(results) == 0

def test_combined_search_text_and_date(temp_index):
    """Комбинированный: текст + дата."""
    from core.searcher import setup_search_parser
    parser = setup_search_parser(temp_index.schema)

    with temp_index.searcher() as searcher:
        params = {
            'query': 'отчёт',
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
            'limit': 10
        }
        results = combined_search(searcher, parser, params, user_roles=["user"])
        assert len(results) == 1
        assert results[0]["path"].endswith("jan_doc.txt")