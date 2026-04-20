from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
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
                        print(f"Ошибка на странице: {e}") #TEST: УДАЛИТЬ
                        continue
            return " ".join(full_text) if full_text else None
        except Exception as e:
            print(f"Ошибка обработки PDF {file_path}: {e}") #TEST: УДАЛИТЬ
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
        Основная метод индексации с пакетной записью и очисткой удалённых файлов.
        - Удаляет из индекса документы, чьи файлы больше не существуют на диске.
        - Извлекает текст многопоточно.
        - Записывает документы пакетами по Config.BATCH_SIZE (защита от MemoryError).
        """
        files_to_index = FileIndexer._get_files_to_index(directory)
        if not files_to_index:
            print_error("Поддерживаемые файлы не найдены")
            return 0, 0

        ix = FileIndexer.get_index(Config.INDEX_DIR)

        #ОЧИСТКА УДАЛЁННЫХ ФАЙЛОВ ИЗ ИНДЕКСА
        deleted_count = 0
        try:
            with ix.searcher() as searcher:
                # Собираем все пути, которые сейчас есть в индексе
                indexed_paths = {fields.get("path") for fields in searcher.all_stored_fields()}

            # Собираем все реальные пути из целевой директории
            valid_paths = {str(f.resolve()) for f in files_to_index}

            # Находим пути, которые есть в индексе, но отсутствуют на диске
            paths_to_remove = indexed_paths - valid_paths

            if paths_to_remove:
                with ix.writer() as writer:
                    for path in paths_to_remove:
                        writer.delete_by_term("path", path)
                deleted_count = len(paths_to_remove)
                print_success(f"Очищено из индекса: {deleted_count} удалённых файлов") #TEST: УДАЛИТЬ
        except Exception as e:
            print_error(f"Ошибка при синхронизации индекса: {e}")

        #МНОГОПОТОЧНОЕ ИЗВЛЕЧЕНИЕ + ПАКЕТНАЯ ЗАПИСЬ
        success = 0
        failed = 0
        processed = 0
        total_files = len(files_to_index)
        batch: List[Dict[str, Any]] = []

        def process_file(file_path: Path) -> Optional[Dict[str, Any]]:
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

        with ThreadPoolExecutor(max_workers=Config.WORKERS) as executor:
            futures = {executor.submit(process_file, f): f for f in files_to_index}
            for future in as_completed(futures):
                doc = future.result()
                if doc:
                    batch.append(doc)
                    success += 1
                else:
                    failed += 1

                processed += 1
                if progress_callback:
                    progress_callback(int(processed / total_files * 100))

                # Пакетная запись в индекс (разгружает память)
                if len(batch) >= Config.BATCH_SIZE:
                    try:
                        with ix.writer() as writer:
                            for d in batch:
                                writer.update_document(**d)
                        batch.clear()
                    except Exception as e:
                        print_error(f"Ошибка записи пакета в индекс: {e}")

        # Записываем оставшийся "хвост"
        if batch:
            try:
                with ix.writer() as writer:
                    for d in batch:
                        writer.update_document(**d)
            except Exception as e:
                print_error(f"Ошибка записи остатка в индекс: {e}")

        # Оптимизация сегментов при большом объёме (ускоряет поиск)
        if total_files > Config.BATCH_SIZE * 100:
            ix.optimize()

        print_success(f"Индексация завершена. Добавлено/обновлено: {success} | Ошибок: {failed}") #TEST: УДАЛИТЬ
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