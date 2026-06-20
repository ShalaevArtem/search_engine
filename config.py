from pathlib import Path
import os

class Config:
    """Конфигурация поисковой системы и индексации файлов"""

    BASE_DIR = Path(__file__).parent
    INDEX_DIR = BASE_DIR / "indexdir"
    NLTK_DATA_DIR = Path(__file__).parent / "nltk_data"

    SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.txt')

    MAX_CACHE_SIZE = 1000
    MAX_SYNONYMS = 5

    PDF_TEXT_LIMIT = 5000
    PDF_MAX_PAGES = 100
    PDF_MIN_SIZE = 1024
    PDF_X_TOLERANCE = 1
    PDF_Y_TOLERANCE = 1
    PDF_LAYOUT = False

    MAX_TEXT_LENGTH = 10_000_000

    FILE_SEARCH_LIMIT = 50

    WORKERS = min(os.cpu_count() or 4, 8)
    BATCH_SIZE = 100

    MAX_QUERY_LENGTH = 200
