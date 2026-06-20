from whoosh.analysis import StemmingAnalyzer, StandardAnalyzer
from typing import TypedDict, Optional
from datetime import datetime
from whoosh.fields import Schema, TEXT, DATETIME, ID, KEYWORD

search_schema = Schema(
    path=ID(stored=True, unique=True),
    filename=TEXT(stored=True, analyzer=StandardAnalyzer()),
    content=TEXT(analyzer=StemmingAnalyzer()),
    last_modified=DATETIME(stored=True),
    roles=KEYWORD(stored=True, commas=True)
)

class SearchResult(TypedDict, total=False):
    path: str
    score: float
    last_modified: Optional[datetime]
    filename: Optional[str]

class CombinedSearchParams(TypedDict):
    query: str
    start_date: str
    end_date: str
    limit: int