from whoosh import fields
from whoosh.analysis import StemmingAnalyzer, StandardAnalyzer

# Схема индекса Whoosh для полнотекстового поиска
search_schema = fields.Schema(
    # Уникальный путь к файлу (индексируется как ID)
    path=fields.ID(
        stored=True,    # Хранится в индексе для быстрого доступа
        unique=True     # Гарантирует уникальность путей
    ),

    # Имя файла со стандартным анализатором (разбиение на слова + нижний регистр)
    filename=fields.TEXT(
        stored=True,    # Сохраняется для отображения в результатах
        analyzer=StandardAnalyzer() # Анализатор без стемминга
    ),

    # Содержимое файла со стемминг-анализатором (нормализация словоформ)
    content=fields.TEXT(
        analyzer=StemmingAnalyzer() # Приводит слова к основе (работает -> работа)
    ),

    # Дата последнего изменения файла
    last_modified=fields.DATETIME(
        stored=True     # Хранится для фильтрации по дате
    )
)

# Типы данных для аннотаций
from typing import Dict, TypedDict

# Результат поиска: словарь с путем, оценкой релевантности и датой изменения
SearchResult = Dict[str, str]

# Параметры для комбинированного поиска (с проверкой типов)
class CombinedSearchParams(TypedDict):
    query: str      # Поисковая фраза
    start_date: str # Начальная дата в формате "YYYY-MM-DD"
    end_date: str   # Конечная дата в формате "ГГГГ-ММ-ДД"
    limit: int      # Максимальное количество результатов
