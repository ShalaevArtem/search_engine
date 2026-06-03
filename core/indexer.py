import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
import pdfplumber
from docx import Document as DocxDocument
from whoosh import index
from config import Config
from models.schemas import search_schema

# Подавление технических предупреждений pdfminer/pdfplumber
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfplumber").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class FileIndexer:
    """Класс для индексации файлов различных форматов (PDF, DOCX, TXT) с использованием Whoosh."""

    @staticmethod
    def extract_pdf_text(file_path: Path) -> Optional[str]:
        """Извлекает текст из PDF-файла с учетом ограничений по размеру и страницам."""
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
                        logger.debug(f"Пропуск страницы PDF {file_path}: {e}")
                        continue
            return " ".join(full_text) if full_text else None
        except Exception as e:
            logger.warning(f"Ошибка чтения PDF {file_path}: {e}")
            return None

    @staticmethod
    def extract_docx_text(file_path: Path) -> str:
        """Извлекает текст из DOCX-файла. Пропускает битые архивы и ссылки."""
        try:
            doc = DocxDocument(file_path)
            parts = []
            for para in doc.paragraphs:
                if para.text:
                    parts.append(para.text)
                    if len(parts) > 100:
                        parts = [" ".join(parts)]
            return " ".join(parts)[:Config.MAX_TEXT_LENGTH]
        except zipfile.BadZipFile:
            logger.warning(f"Пропуск битого/ссылочного DOCX: {file_path}")
            return ""
        except Exception as e:
            logger.warning(f"Ошибка обработки DOCX {file_path}: {e}")
            return ""

    @staticmethod
    def get_index(index_dir: Path) -> index.Index:
        """Открывает существующий индекс или создает новый."""
        try:
            if not index_dir.exists():
                index_dir.mkdir(parents=True)
                return index.create_in(index_dir, schema=search_schema)
            if index.exists_in(index_dir):
                return index.open_dir(index_dir)
            return index.create_in(index_dir, schema=search_schema)
        except Exception as e:
            logger.error(f"Ошибка открытия индекса: {e}")
            raise

    @staticmethod
    def index_files(directory: Path, user_roles: list[str], progress_callback: Callable[[int], None] = None) -> Tuple[
        int, int]:
        """
        Индексирует ТОЛЬКО файлы, доступные указанным ролям.
        Возвращает (успешно_проиндексировано, ошибок_чтения).
        """
        from core.access_control import check_file_access, get_allowed_roles_for_path

        raw_files = FileIndexer._get_files_to_index(directory)
        if not raw_files:
            logger.warning("Поддерживаемые файлы не найдены")
            return 0, 0

        # Предварительная фильтрация по ACL (экономит ресурсы и не утекает метаданные)
        accessible_files = [
            f for f in raw_files
            if check_file_access(str(f.resolve()), user_roles)
        ]

        if not accessible_files:
            logger.info("Нет файлов с доступом для указанных ролей")
            return 0, 0

        ix = FileIndexer.get_index(Config.INDEX_DIR)

        # Очистка удалённых/недоступных файлов из индекса
        try:
            with ix.searcher() as searcher:
                indexed_paths = {fields.get("path") for fields in searcher.all_stored_fields()}
            valid_paths = {str(f.resolve()) for f in accessible_files}
            paths_to_remove = indexed_paths - valid_paths

            if paths_to_remove:
                with ix.writer() as writer:
                    for path in paths_to_remove:
                        writer.delete_by_term("path", path)
                logger.info(f"Очищено из индекса: {len(paths_to_remove)} файлов")
        except Exception as e:
            logger.error(f"Ошибка синхронизации индекса: {e}")

        # Многопоточное извлечение + запись
        success = 0
        failed = 0
        processed = 0
        total = len(accessible_files)

        def process_file(file_path: Path) -> Optional[Dict[str, Any]]:
            try:
                content = FileIndexer._extract_text(file_path)
                if not content:
                    return None

                allowed_roles = get_allowed_roles_for_path(str(file_path.resolve()))
                if not allowed_roles:
                    return None

                return {
                    'path': str(file_path.resolve()),
                    'filename': file_path.name,
                    'content': content,
                    'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime),
                    'roles': ','.join(allowed_roles)
                }
            except Exception as e:
                logger.warning(f"Ошибка обработки {file_path}: {e}")
                return None

        writer = None
        try:
            writer = ix.writer(limitmb=512)
            with ThreadPoolExecutor(max_workers=Config.WORKERS) as executor:
                futures = {executor.submit(process_file, f): f for f in accessible_files}
                for future in as_completed(futures):
                    doc = future.result()
                    if doc:
                        writer.update_document(**doc)
                        success += 1
                    else:
                        failed += 1

                    processed += 1
                    if progress_callback:
                        progress_callback(int(processed / total * 100))

            writer.commit()
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            if writer:
                writer.cancel()
            raise
        finally:
            # Гарантированное освобождение ресурсов
            if writer:
                try:
                    writer.close()
                except:
                    pass

        logger.info(f"Индексация завершена. Успешно: {success} | Ошибок: {failed}")
        return success, failed

    @staticmethod
    def _get_files_to_index(directory: Path) -> List[Path]:
        """Собирает файлы для индексации. Пропускает ссылки, применяет фильтр размера только к PDF."""
        files = []
        for f in directory.rglob('*'):
            if not f.is_file():
                continue
            # Пропускаем символические ссылки (часто ломают парсеры в node_modules)
            if f.is_symlink():
                continue
            if f.suffix.lower() not in Config.SUPPORTED_EXTENSIONS:
                continue

            # Лимит размера только для PDF
            if f.suffix.lower() == '.pdf' and f.stat().st_size < Config.PDF_MIN_SIZE:
                continue

            files.append(f)
        return files

    @staticmethod
    def _extract_text(file_path: Path) -> Optional[str]:
        """Определяет тип файла и вызывает соответствующий экстрактор."""
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return FileIndexer.extract_pdf_text(file_path)
        elif ext == '.docx':
            return FileIndexer.extract_docx_text(file_path)
        elif ext == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(Config.MAX_TEXT_LENGTH)
            except Exception as e:
                logger.warning(f"Ошибка чтения TXT {file_path}: {e}")
                return None
        return None