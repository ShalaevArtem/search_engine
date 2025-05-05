from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from typing import Optional, Tuple, Callable

import pdfplumber
from docx import Document as DocxDocument
from whoosh import index
from whoosh.writing import IndexWriter

from config import Config
from models.schemas import search_schema
from .utils import print_error, print_success


class FileIndexer:
    """Класс для индексации файлов различных форматов (PDF, DOCX, TXT) с использованием Whoosh."""

    @staticmethod
    def extract_pdf_text(file_path: Path) -> Optional[str]:
        """
        Извлекает текст из PDF-файла с учетом ограничений по размеру и количеству страниц.
        Проверяет минимальный размер файла, затем открывает PDF через pdfplumber.
        Извлекает текст с каждой страницы (до максимального числа страниц).
        Ограничивает длину текста с каждой страницы.
        Возвращает объединенный текст или None, если текст не найден или файл слишком мал.
        """
        try:
            if file_path.stat().st_size < Config.PDF_MIN_SIZE:
                return None

            full_text = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[:Config.PDF_MAX_PAGES]:
                    try:
                        text = page.extract_text(
                            x_tolerance=Config.PDF_X_TOLERANCE,
                            y_tolerance=Config.PDF_Y_TOLERANCE
                        )
                        if text:
                            full_text.append(text[:Config.PDF_TEXT_LIMIT])
                    except Exception as e:
                        print(f"Ошибка на странице: {e}")
                        continue

            return " ".join(full_text) if full_text else None
        except Exception as e:
            print(f"Ошибка обработки PDF {file_path}: {e}")
            return None

    @staticmethod
    def extract_docx_text(file_path: Path) -> str:
        """
        Извлекает текст из DOCX-файла.
        Читает все параграфы документа, аккумулирует текст.
        Для контроля памяти при больших документах объединяет текст каждые 100 параграфов.
        Возвращает текст, обрезанный по максимальной длине из конфигурации.
        """
        try:
            doc = DocxDocument(file_path)
            parts = []
            for para in doc.paragraphs:
                if para.text:
                    parts.append(para.text)
                    # Контроль памяти для больших документов
                    if len(parts) > 100:
                        parts = [" ".join(parts)]
            return " ".join(parts)[:Config.MAX_TEXT_LENGTH]
        except Exception as e:
            print_error(f"DOCX processing error {file_path}: {e}")
            return ""

    @staticmethod
    def create_or_open_index(index_dir: Path) -> index.Index:
        """
        Создает новый индекс Whoosh в указанной директории.
        Если директория не существует, создает ее.
        Возвращает объект индекса.
        """
        if not index_dir.exists():
            index_dir.mkdir(parents=True)
        return index.create_in(index_dir, schema=search_schema)

    @staticmethod
    def get_index(index_dir):
        """
        Открывает существующий индекс или создает новый, если индекс отсутствует.
        Обрабатывает ошибки открытия индекса.
        Возвращает объект индекса.
        """
        try:
            if not index_dir.exists():
                index_dir.mkdir(parents=True)
                return index.create_in(index_dir, schema=search_schema)

            if index.exists_in(index_dir):
                return index.open_dir(index_dir)

            return index.create_in(index_dir, schema=search_schema)
        except Exception as e:
            print_error(f"Ошибка открытия индекса: {e}")
            raise

    @staticmethod
    def index_files(directory: Path, progress_callback: Callable[[int], None] = None) -> Tuple[int, int]:
        """
        Основной метод индексации файлов из директории с многопоточной обработкой.
        - Получает список файлов для индексации.
        - Параллельно извлекает текст и метаданные из файлов.
        - Записывает документы в индекс в однопоточном режиме.
        - Вызывает callback с прогрессом, если он передан.
        - Оптимизирует индекс при большом количестве файлов.
        - Возвращает количество успешно и неуспешно обработанных файлов.
        """
        files = FileIndexer._get_files_to_index(directory)
        if not files:
            print_error("Поддерживаемые файлы не найдены")
            return 0, 0

        ix = FileIndexer.create_or_open_index(Config.INDEX_DIR)
        docs: List[Dict[str, Any]] = []
        success = 0
        failed = 0

        def process_file(file_path: Path) -> Dict[str, Any]:
            # Вспомогательная функция для извлечения текста и метаданных из одного файла
            try:
                content = FileIndexer._extract_text(file_path)
                last_modified = datetime.fromtimestamp(file_path.stat().st_mtime)
                return {
                    'path': str(file_path.resolve()),
                    'filename': file_path.name,
                    'content': content,
                    'last_modified': last_modified
                }
            except Exception as e:
                print_error(f"Ошибка обработки файла {file_path}: {e}")
                return None

        total_files = len(files)
        processed = 0

        # Многопоточная обработка файлов для ускорения извлечения текста
        with ThreadPoolExecutor(max_workers=Config.WORKERS) as executor:
            futures = [executor.submit(process_file, f) for f in files]
            for future in as_completed(futures):
                doc = future.result()
                if doc:
                    docs.append(doc)
                    success += 1
                else:
                    failed += 1
                processed += 1
                if progress_callback:
                    progress = int(processed / total_files * 100)
                    progress_callback(progress)

        # Запись всех документов в индекс в однопоточном режиме
        with ix.writer() as writer:
            for doc in docs:
                writer.update_document(**doc)

        print_success(f"Проиндексировано файлов: {success}")
        if failed:
            print_error(f"Ошибок при обработке файлов: {failed}")

        # Оптимизация индекса при большом количестве документов
        if len(files) > 10000:
            ix.optimize()

        return success, failed

    @staticmethod
    def _get_files_to_index(directory: Path) -> List[Path]:
        """
        Рекурсивно собирает список файлов с поддерживаемыми расширениями для индексации.
        Фильтрует файлы по расширению и минимальному размеру.
        """
        return [
            f for f in directory.rglob('*')
            if f.suffix.lower() in Config.SUPPORTED_EXTENSIONS
               and f.stat().st_size >= Config.PDF_MIN_SIZE
        ]

    @staticmethod
    def _process_batch(writer: IndexWriter, batch: List[Path]) -> Tuple[int, int]:
        """
        Обрабатывает пакет файлов: извлекает текст и добавляет документы в индекс.
        Используется для пакетной индексации (не используется в основном методе).
        Возвращает количество успешно обработанных файлов и общий размер пакета.
        """
        success = 0
        for file_path in batch:
            text = FileIndexer._extract_text(file_path)
            try:
                print(f"Индексируем файл: {file_path.name}, тип: {type(file_path.name)}")
                writer.add_document(
                    path=str(file_path.absolute()),
                    filename=str(file_path.name.lower()),
                    content=text,
                    last_modified=datetime.fromtimestamp(file_path.stat().st_mtime)
                )
                success += 1
            except Exception as e:
                print_error(f"Indexing error {file_path}: {e}")
        return success, len(batch)

    @staticmethod
    def _extract_text(file_path: Path) -> Optional[str]:
        """
        Определяет тип файла по расширению и вызывает соответствующий метод для извлечения текста.
        Поддерживаются PDF, DOCX и TXT.
        Возвращает извлеченный текст или None, если формат не поддерживается.
        """
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return FileIndexer.extract_pdf_text(file_path)
        elif ext == '.docx':
            return FileIndexer.extract_docx_text(file_path)
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(Config.MAX_TEXT_LENGTH)
        return None