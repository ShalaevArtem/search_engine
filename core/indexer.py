import time
import logging
import zipfile
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Callable
from docx import Document as DocxDocument
from whoosh import index
from config import Config
from models.schemas import search_schema

logging.getLogger("pdfminer").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

class FileIndexer:
    """Класс для индексированя файлов форматов (PDF, DOCX, TXT) с использованием Whoosh."""

    @staticmethod
    def extract_pdf_text(file_path: Path) -> Optional[str]:
        """Извлекает текст из PDF-файла с учетом ограничений по размеру и страницам."""
        try:
            if file_path.stat().st_size < Config.PDF_MIN_SIZE:
                return None

            doc = fitz.open(str(file_path))
            full_text = []
            total_len = 0
            max_pages = min(len(doc), Config.PDF_MAX_PAGES)

            for page_num in range(max_pages):
                page = doc.load_page(page_num)
                text = page.get_text()
                if not text:
                    continue

                if total_len + len(text) > Config.MAX_TEXT_LENGTH:
                    remaining = Config.MAX_TEXT_LENGTH - total_len
                    full_text.append(text[:remaining])
                    break

                full_text.append(text)
                total_len += len(text)

            doc.close()
            return "\n".join(full_text) if full_text else None

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
        Многопоточное извлечение, пропуск неизменённых файлов, PyMuPDF для PDF.
        """
        from core.access_control import check_file_access, get_allowed_roles_for_path

        logger.info(f"Начало индексирования")
        t_start = time.perf_counter()
        logger.info(f"Директория: {directory}")

        raw_files = FileIndexer._get_files_to_index(directory)
        logger.info(f"Найдено файлов (все форматы): {len(raw_files)}")
        if not raw_files:
            logger.warning("Поддерживаемые файлы не найдены")
            return 0, 0

        accessible_files = []
        for f in raw_files:
            path_str = str(f.resolve())
            has_access = check_file_access(path_str, user_roles)
            logger.debug(f"ACL check: {path_str} -> {has_access}")
            if has_access:
                accessible_files.append(f)

        logger.info(f"Файлов после фильтра по правилам доступа: {len(accessible_files)}")
        if not accessible_files:
            logger.info("Нет файлов с доступом для указанных ролей")
            return 0, 0

        ix = FileIndexer.get_index(Config.INDEX_DIR)
        logger.info(f"Индекс открыт: {Config.INDEX_DIR}")

        indexed_docs = {}
        try:
            with ix.searcher() as searcher:
                for fields in searcher.all_stored_fields():
                    p = fields.get("path")
                    if p:
                        lm = fields.get("last_modified")
                        if lm:
                            indexed_docs[p] = lm
        except Exception as e:
            logger.warning(f"Не удалось загрузить существующий индекс для проверки mtime: {e}")

        files_to_reindex = []
        skipped_unchanged = 0
        for f in accessible_files:
            path_str = str(f.resolve())
            mtime = datetime.fromtimestamp(f.stat().st_mtime)

            if path_str in indexed_docs:
                indexed_mtime = indexed_docs[path_str]
                if indexed_mtime and abs((indexed_mtime - mtime).total_seconds()) < 1:
                    skipped_unchanged += 1
                    continue

            files_to_reindex.append(f)

        logger.info(f"Файлов для переиндексирования: {len(files_to_reindex)} (пропущено неизменённых: {skipped_unchanged})")

        try:
            with ix.searcher() as searcher:
                indexed_paths = {fields.get("path") for fields in searcher.all_stored_fields()}

            valid_paths = {str(f.resolve()) for f in accessible_files}
            paths_to_remove = indexed_paths - valid_paths

            if paths_to_remove:
                logger.info(f"Удаление из индекса: {len(paths_to_remove)} файлов")
                with ix.writer() as writer:
                    for path in paths_to_remove:
                        logger.debug(f"  Удаление: {path}")
                        writer.delete_by_term("path", path)
        except Exception as e:
            logger.error(f"Ошибка синхронизации индекса: {e}")

        success = 0
        failed = 0
        total = len(files_to_reindex)

        def _extract_one(file_path: Path) -> Optional[dict]:
            """Извлекает текст и метаданные одного файла. Вызывается в пуле потоков."""
            try:
                content = FileIndexer._extract_text(file_path)
                if not content:
                    logger.warning(f"  Текст не извлечён: {file_path}")
                    return None

                allowed_roles = get_allowed_roles_for_path(str(file_path.resolve()))
                if not allowed_roles:
                    logger.warning(f"  Нет ролей для файла: {file_path}")
                    return None

                return {
                    'path': str(file_path.resolve()),
                    'filename': file_path.name,
                    'content': content,
                    'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime),
                    'roles': ','.join(allowed_roles)
                }
            except Exception as e:
                logger.error(f"  ОШИБКА обработки {file_path}: {type(e).__name__}: {e}")
                return None

        writer = None
        try:
            logger.info(f"Создание writer")
            writer = ix.writer(limitmb=1024)
            logger.info(f"Writer создан, начало обработки {total} файлов")

            if total == 0:
                logger.info("Нет файлов для индексирования (все актуальны)")
            else:
                with ThreadPoolExecutor(max_workers=Config.WORKERS) as executor:
                    future_to_file = {
                        executor.submit(_extract_one, f): f for f in files_to_reindex
                    }

                    for i, future in enumerate(as_completed(future_to_file)):
                        file_path = future_to_file[future]
                        result = future.result()

                        if result:
                            writer.update_document(**result)
                            success += 1
                            logger.debug(f"  УСПЕХ: {result['path'][:80]}")
                        else:
                            failed += 1
                            logger.debug(f"  ПРОПУЩЕН: {file_path}")

                        if progress_callback and total > 0:
                            progress_callback(int((i + 1) / total * 100))

            logger.info(f"Commit индекса")
            writer.commit()
            elapsed = time.perf_counter() - t_start
            logger.info(f"Индексирование завершено за {elapsed:.2f} сек ===")
            logger.info(f"Успешно: {success} | Ошибок: {failed} | Пропущено неизменённых: {skipped_unchanged}")
            return success, failed

        except Exception as e:
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА ИНДЕКСИРОВАНИЯ: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Трейс: {traceback.format_exc()}")
            if writer:
                try:
                    writer.cancel()
                except:
                    pass
            raise

        finally:
            if writer:
                try:
                    writer.close()
                except:
                    pass

    @staticmethod
    def _get_files_to_index(directory: Path) -> List[Path]:
        """Собирает файлы для индексирования. Пропускает ссылки, применяет фильтр размера только к PDF."""
        files = []
        for f in directory.rglob('*'):
            if not f.is_file():
                continue
            if f.is_symlink():
                continue
            if f.suffix.lower() not in Config.SUPPORTED_EXTENSIONS:
                continue

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