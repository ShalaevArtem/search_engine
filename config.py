from pathlib import Path
import os
from typing import Dict, Any

class Config:
    """Конфигурация поисковой системы и индексации файлов"""

    # --- Пути ---
    BASE_DIR = Path(__file__).parent
    # Директория для хранения индекса Whoosh
    INDEX_DIR = BASE_DIR / "indexdir"

    # --- Поддерживаемые форматы файлов для индексации ---
    SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.txt')

    # --- Настройки кэширования ---
    MAX_CACHE_SIZE = 1000   # Максимальное количество элементов в кэше синонимов и переводов
    MAX_SYNONYMS = 5        # Максимальное количество синонимов для расширенного поиска
    TRANSLATION_CACHE: Dict[str, str] = {}  # Кэш для переводов слов (если используется)
    SYNONYM_CACHE: Dict[str, Any] = {}      # Кэш для синонимов слов

    # --- Оптимизация обработки PDF ---
    PDF_TEXT_LIMIT = 5000   # Максимальное количество символов текста, извлекаемого с одной страницы PDF
    PDF_MAX_PAGES = 1000    # Максимальное количество страниц PDF для обработки (ограничение по времени и ресурсам)
    PDF_MIN_SIZE = 1024     # Минимальный размер PDF-файла в байтах (1 КБ), чтобы избежать обработки пустых или очень маленьких файлов
    PDF_X_TOLERANCE = 1     # Параметр точности по горизонтали при извлечении текста из PDF (pdfplumber)
    PDF_Y_TOLERANCE = 1     # Параметр точности по вертикали при извлечении текста из PDF (pdfplumber)
    PDF_LAYOUT = False      # Флаг, влияющий на режим извлечения текста (ускорение или точность)

    # --- Настройки для DOCX и TXT файлов ---
    MAX_TEXT_LENGTH = 10_000_000    # Максимальная длина текста для индексации (примерно 10 МБ)

    # --- Настройки поиска по имени файла ---
    FILE_SEARCH_LIMIT = 50  # Максимальное количество результатов при поиске по имени файла

    # --- Параллельная обработка файлов ---
    WORKERS = min(os.cpu_count() or 4, 8)   # Количество потоков для многопоточной обработки (от 4 до 8)
    BATCH_SIZE = 100    # Размер пакета файлов для пакетной обработки
