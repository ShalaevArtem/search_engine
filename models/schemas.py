from whoosh import fields
from whoosh.analysis import StemmingAnalyzer, StandardAnalyzer
from typing import TypedDict, Optional, Dict
from datetime import datetime
from whoosh.fields import Schema, TEXT, DATETIME, ID, KEYWORD

# Схема индекса Whoosh для полнотекстового поиска
search_schema = Schema(
    # Уникальный путь к файлу (индексируется как ID)
    path=ID(
        stored=True,    # Хранится в индексе для быстрого доступа
        unique=True     # Гарантирует уникальность путей
    ),

    # Имя файла со стандартным анализатором (разбиение на слова + нижний регистр)
    filename=TEXT(
        stored=True,    # Сохраняется для отображения в результатах
        analyzer=StandardAnalyzer() # Анализатор без стемминга
    ),

    # Содержимое файла со стемминг-анализатором (нормализация словоформ)
    content=TEXT(
        analyzer=StemmingAnalyzer() # Приводит слова к основе (работает -> работа)
    ),

    # Дата последнего изменения файла
    last_modified=DATETIME(
        stored=True     # Хранится для фильтрации по дате
    ),

    roles=KEYWORD(stored=True, commas=True) # Список ролей через запятую
)

# Результат поиска: словарь с путем, оценкой релевантности и датой изменения
#SearchResult = Dict[str, str]
class SearchResult(TypedDict, total=False):
    path: str
    score: float
    last_modified: Optional[datetime]
    filename: Optional[str]

# Параметры для комбинированного поиска (с проверкой типов)
class CombinedSearchParams(TypedDict):
    query: str      # Поисковая фраза
    start_date: str # Начальная дата в формате "YYYY-MM-DD"
    end_date: str   # Конечная дата в формате "ГГГГ-ММ-ДД"
    limit: int      # Максимальное количество результатов
