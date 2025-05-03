from pathlib import Path
import os
from typing import Dict, Any

class Config:
    """Конфигурация поисковой системы"""

    # Пути
    BASE_DIR = Path(__file__).parent
    INDEX_DIR = BASE_DIR / "indexdir"

    # Поддерживаемые форматы
    SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.txt')

    # Настройки кэширования
    MAX_CACHE_SIZE = 1000
    MAX_SYNONYMS = 5
    TRANSLATION_CACHE: Dict[str, str] = {}
    SYNONYM_CACHE: Dict[str, Any] = {}

    # Оптимизация PDF
    PDF_TEXT_LIMIT = 5000  # Лимит символов на страницу
    PDF_MAX_PAGES = 1000  # Максимальное количество страниц
    PDF_MIN_SIZE = 1024  # 1KB минимальный размер
    PDF_X_TOLERANCE = 1  # Параметры извлечения текста
    PDF_Y_TOLERANCE = 1
    PDF_LAYOUT = False  # Ускорение обработки

    # Настройки DOCX/TXT
    MAX_TEXT_LENGTH = 10_000_000  # 10MB лимит

    # Настройки поиска по имени файла
    FILE_SEARCH_LIMIT = 50  # Максимальное количество результатов

    # Параллельная обработка
    WORKERS = min(os.cpu_count() or 4, 8)  # 4-8 потоков
    BATCH_SIZE = 100  # Размер пакета файлов
