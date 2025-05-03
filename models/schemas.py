from whoosh import fields
from whoosh.analysis import StemmingAnalyzer, StandardAnalyzer

# Схема индекса
search_schema = fields.Schema(
    path=fields.ID(stored=True, unique=True),
    filename=fields.TEXT(stored=True, analyzer=StandardAnalyzer()),
    content=fields.TEXT(analyzer=StemmingAnalyzer()),
    last_modified=fields.DATETIME(stored=True)
)

# Типы данных
from typing import Dict, TypedDict
SearchResult = Dict[str, str]

class CombinedSearchParams(TypedDict):
    query: str
    start_date: str  # Формат: "YYYY-MM-DD"
    end_date: str    # Формат: "YYYY-MM-DD"
    limit: int
