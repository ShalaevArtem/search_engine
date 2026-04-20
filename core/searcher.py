import logging
import re
import string
import traceback

import nltk
from datetime import datetime, time, date, timedelta
from functools import lru_cache
from typing import List
from pathlib import Path
import pymorphy3
from ru_synonyms import SynonymsGraph
import sys

from whoosh.analysis import StandardAnalyzer
from whoosh.qparser import QueryParser, FuzzyTermPlugin, OrGroup
from whoosh.query import Term, And, Or, DateRange, FuzzyTerm, Wildcard
from nltk import word_tokenize
from nltk.corpus import wordnet as wn
from ru_synonyms import SynonymsGraph
from razdel import tokenize

from config import Config
from models.schemas import SearchResult
from .utils import print_error

def validate_query(query: str) -> tuple[bool, str]:
    """Проверяет длину и наличие опасных символов."""
    if not query or not query.strip():
        return False, "Запрос пустой"
    if len(query) > Config.MAX_QUERY_LENGTH:
        return False, f"Запрос слишком длинный (макс {Config.MAX_QUERY_LENGTH} символов)"
    return True, ""

# --- Логгер для отладки поиска (TEST: УДАЛИТЬ)---
search_logger = logging.getLogger("search_debug")
if not search_logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    search_logger.addHandler(_handler)
    search_logger.setLevel(logging.INFO)

# Логирование для отладки и мониторинга
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Инициализация инструментов для русского языка (Natasha, ru_synonyms)
morph = pymorphy3.MorphAnalyzer()
sg = SynonymsGraph()

#Локальная папка для NLTK данных
nltk_data_dir = Path(__file__).parent.parent / "nltk_data"
if nltk_data_dir.exists() and str(nltk_data_dir) not in nltk.data.path:
    nltk.data.path.append(str(nltk_data_dir))

def lemmatize_ru(word):
    """Лемматизация русского слова через pymorphy3."""
    if not word or word.strip() in string.punctuation:
        return word
    p = morph.parse(word)[0]
    return p.normal_form

def detect_language(word: str) -> str:
    """
    Определяет язык слова: 'ru' для русского, 'en' для английского, иначе 'unknown'.
    """
    if re.fullmatch(r'[а-яёА-ЯЁ-]+', word):
        return 'ru'
    elif re.fullmatch(r'[a-zA-Z-]+', word):
        return 'en'
    return 'unknown'

@lru_cache(maxsize=Config.MAX_CACHE_SIZE)
def get_synonyms(word: str) -> List:
    """Получает список синонимов для слова (русский и английский).
    Для русского использует Natasha и ru_synonyms, для английского - WordNet.
    Результат кэшируется для ускорения повторных запросов."""
    lang = detect_language(word)

    if lang == 'ru':
        lemma = lemmatize_ru(word)
        if sg.is_in_dictionary(lemma):
            synonyms = list(sg.get_list(lemma))
            return synonyms if synonyms else [lemma]
        else:
            return [lemma]
    elif lang == 'en':
        synonyms = set()
        for syn in wn.synsets(word):
            for lemma in syn.lemmas():
                synonyms.add(lemma.name().replace('_', ' '))
        return list(synonyms) if synonyms else [word]
    else:
        return [word]

@lru_cache(maxsize=Config.MAX_CACHE_SIZE)
def get_cache_synonyms(word):
    """ Кэшированный вызов функции получения синонимов для слова. """
    return get_synonyms(word)

def setup_search_parser(schema):
    """
    Создаёт и настраивает парсер Whoosh для поиска по содержимому.
    Добавляет поддержку нечеткого поиска (FuzzyTerm).
    """
    parser = QueryParser("content", schema, group=OrGroup)
    parser.add_plugin(FuzzyTermPlugin())
    return parser

def tokenize_ru(text: str) -> List[str]:
    """
    Токенизация русского текста с помощью razdel.
    Возвращает список токенов.
    """
    return [t.text for t in tokenize(text)]

def tokenize_en(text: str) -> List[str]:
    """
    Токенизация английского текста.
    Сохраняет апострофы в сокращениях (don't, it's), убирает пунктуацию.
    """
    return re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())

def tokenize_text(text: str, lang: str) -> List[str]:
    """
    Токенизация текста в зависимости от языка.
    Для русского - razdel, для английского - nltk.word_tokenize.
    """
    if lang == 'ru':
        # Для русского используем Natasha
        return [token.lower() for token in tokenize_ru(text)]
    elif lang == 'en':
        return tokenize_en(text)
    return text.lower().split()


def search_index(searcher, parser, query_str: str, limit: int = 10, stop_words=None) -> List[SearchResult]:
    if stop_words is None:
        stop_words = set()

    search_logger.info(f"ЗАПРОС: '{query_str}'") #TEST: УДАЛИТЬ

    # Прямой поиск
    try:
        query = parser.parse(query_str)
        results = searcher.search(query, limit=limit, terms=True)
        if results:
            results_list = list(results)
            search_logger.info(f"Поиск с расширением: найдено {len(results_list)} документов") #TEST: УДАЛИТЬ

            formatted = []
            for hit in results_list:
                matched = []
                try:
                    # matched_terms() может отсутствовать или вернуть итератор, который нельзя перебрать
                    matched = list(set(t[1] for t in hit.matched_terms() if t[0] == 'content'))
                except AttributeError:
                    # Метод не поддерживается в этой версии Whoosh → просто возвращаем пустой список
                    matched = []
                except Exception as ex:
                    search_logger.error(f"matched_terms error: {type(ex).__name__}: {ex}") #TEST: УДАЛИТЬ
                    matched = []

                formatted.append({
                    'path': hit['path'],
                    'score': hit.score,
                    'last_modified': hit.get('last_modified'),
                    'matched_terms': matched
                })
            return formatted
    except Exception as e:
        search_logger.error(f"Ошибка при прямом поиске: {e}") #TEST: УДАЛИТЬ

    # Поиск с расширением (Or + бустинг)
    try:
        lang = detect_language(query_str)
        tokens = tokenize_text(query_str, lang)
        words = [w.lower() for w in tokens if w not in stop_words and w not in string.punctuation]
        search_logger.info(f"Токены: {words}") #TEST: УДАЛИТЬ

        synonym_queries = []
        for word in words:
            synonyms = get_cache_synonyms(word)
            search_logger.info(f"  '{word}' → {synonyms[:Config.MAX_SYNONYMS]}") #TEST: УДАЛИТЬ
            if synonyms:
                synonym_queries.append(Or([Term("content", s) for s in synonyms[:Config.MAX_SYNONYMS]]))

        if synonym_queries:
            # .boost = value (свойство, а не метод)
            synonym_expansion = Or(synonym_queries)
            synonym_expansion.boost = 0.6

            original_query = parser.parse(query_str)
            original_query.boost = 2.0

            final_query = Or([original_query, synonym_expansion])

            results = searcher.search(final_query, limit=limit, terms=True)
            if results:
                results_list = list(results)
                search_logger.info(f"Поиск с расширением: найдено {len(results_list)} документов") #TEST: УДАЛИТЬ

                formatted = []
                for hit in results_list:
                    matched = []
                    try:
                        # Декодируем байты в строки UTF-8
                        matched = list(set(
                            t[1].decode('utf-8') if isinstance(t[1], bytes) else str(t[1])
                            for t in hit.matched_terms()
                            if t[0] == 'content'
                        ))
                    except AttributeError:
                        # Метод не поддерживается в этой версии Whoosh → просто возвращаем пустой список
                        matched = []
                    except Exception as ex:
                        search_logger.error(f"matched_terms error: {type(ex).__name__}: {ex}") #TEST: УДАЛИТЬ
                        matched = []

                    formatted.append({
                        'path': hit['path'],
                        'score': hit.score,
                        'last_modified': hit.get('last_modified'),
                        'matched_terms': matched
                    })
                return formatted

        search_logger.info("Ничего не найдено") #TEST: УДАЛИТЬ
        return []
    except Exception as e:
        search_logger.error(f"Ошибка при поиске с синонимами: {type(e).__name__}: {e}\n{traceback.format_exc()}") #TEST: УДАЛИТЬ
        return []

def search_time_range(searcher, start_date_str: str, end_date_str: str, limit: int = 10) -> List[SearchResult]:
    """
    Поиск документов по временному диапазону (дата изменения).
    Поддерживает ключевые слова 'сегодня' и 'вчера', а также формат YYYY-MM-DD.
    """
    start_date = None
    end_date = None
    try:
        # Обработка относительных дат и строковых дат
        if start_date_str and start_date_str.lower() == 'сегодня':
            start_date = date.today()
        elif start_date_str and start_date_str.lower() == 'вчера':
            start_date = date.today() - timedelta(days=1)
        elif start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

        if end_date_str and end_date_str.lower() == 'сегодня':
            end_date = date.today()
        elif end_date_str and end_date_str.lower() == 'вчера':
            end_date = date.today() - timedelta(days=1)
        elif end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        results = []
        if start_date and end_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())

            date_query = DateRange("last_modified", start_datetime, end_datetime)
            hits = searcher.search(date_query, limit=limit)
            for hit in hits:
                results.append({
                    'path': hit['path'],
                    'score': hit.score,
                    'last_modified': hit['last_modified']
                })
        elif start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            date_query = DateRange("last_modified", start_datetime, datetime.combine(date.today(), datetime.max.time()))
            hits = searcher.search(date_query, limit=limit)
            for hit in hits:
                results.append({
                    'path': hit['path'],
                    'score': hit.score,
                    'last_modified': hit['last_modified']
                })
        elif end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())
            date_query = DateRange("last_modified", datetime.combine(date(1970, 1, 1), datetime.min.time()),
                                   end_datetime)
            hits = searcher.search(date_query, limit=limit, terms=True)
            for hit in hits:
                results.append({
                    'path': hit['path'],
                    'score': hit.score,
                    'last_modified': hit['last_modified']
                })

    except ValueError:
        print_error("Неверный формат даты. Используйте YYYY-MM-DD или 'сегодня'/'вчера'.")
        return []
    return results


def combined_search(searcher, parser, params: dict, stop_words=None) -> List[SearchResult]: #ДОДЕЛАТЬ (КАК search_index)
    if stop_words is None:
        stop_words = set()

    search_logger.info(f"КОМБО: '{params['query']}' | Даты: {params['start_date']} → {params['end_date']}") #TEST: УДАЛИТЬ

    try:
        start_dt = datetime.strptime(params['start_date'], "%Y-%m-%d").date()
        end_dt = datetime.strptime(params['end_date'], "%Y-%m-%d").date()
        date_query = DateRange(
            "last_modified",
            datetime.combine(start_dt, time.min),
            datetime.combine(end_dt, time.max)
        )

        # Прямой поиск + дата
        original_query = parser.parse(params['query'])
        direct_query = And([original_query, date_query])
        results = searcher.search(direct_query, limit=params.get('limit', 10), terms=True)
        if results:
            results_list = list(results)
            search_logger.info(f"Прямой комбо: найдено {len(results_list)} документов")
            return [{
                'path': hit['path'],
                'score': hit.score,
                'last_modified': hit.get('last_modified')
            } for hit in results_list]

        # Поиск с синонимами + дата (Or + бустинг)
        lang = detect_language(params['query'])
        tokens = tokenize_text(params['query'], lang)
        words = [w.lower() for w in tokens if w not in stop_words and w not in string.punctuation]
        search_logger.info(f"Токены для комбо: {words}") #TEST: УДАЛИТЬ

        synonym_queries = []
        for word in words:
            synonyms = get_cache_synonyms(word)
            search_logger.info(f"'{word}' → {synonyms[:Config.MAX_SYNONYMS]}")
            if synonyms:
                synonym_queries.append(Or([Term("content", s) for s in synonyms[:Config.MAX_SYNONYMS]]))

        if synonym_queries:
            synonym_expansion = Or(synonym_queries)
            synonym_expansion.boost = 0.6

            original_boosted = parser.parse(params['query'])
            original_boosted.boost = 2.0

            text_query = Or([original_boosted, synonym_expansion])
            combined_query = And([text_query, date_query])

            results = searcher.search(combined_query, limit=params.get('limit', 10), terms=True)
            if results:
                results_list = list(results)
                search_logger.info(f"Комбо по синонимам: найдено {len(results_list)} документов") #TEST: УДАЛИТЬ
                return [{
                    'path': hit['path'],
                    'score': hit.score,
                    'last_modified': hit.get('last_modified')
                } for hit in results_list]

        search_logger.info("Комбо поиск не дал результатов") #TEST: УДАЛИТЬ
        return []
    except Exception as e:
        logger.error(f"Ошибка в combined_search: {e}")
        return []

def _normalize_filename(filename):
    """
    Приводит имя файла к строке в нижнем регистре для сравнения.
    Поддерживает bytes, str, int.
    """
    if isinstance(filename, bytes):
        try:
            return filename.decode('utf-8').lower()
        except UnicodeDecodeError:
            return None
    elif isinstance(filename, str):
        return filename.lower()
    elif isinstance(filename, int):
        return str(filename).lower()
    else:
        return None

def search_by_filename(searcher, filename: str) -> List[SearchResult]:
    """Поиск документов по имени файла"""
    filename_query = filename.strip().lower()
    if not filename_query:
        return []

    # Нативные запросы Whoosh: точное начало + нечёткое + wildcard
    prefix_q = FuzzyTerm("filename", filename_query, boost=2.0)
    wildcard_q = Wildcard("filename", f"*{filename_query}*")
    fuzzy_q = FuzzyTerm("filename", filename_query, maxdist=2)

    query = Or([prefix_q, wildcard_q, fuzzy_q])
    results = searcher.search(query, limit=Config.FILE_SEARCH_LIMIT)

    return [{
        'path': hit['path'],
        'filename': hit.get('filename', ''),
        'score': hit.score,
        'last_modified': hit.get('last_modified')
    } for hit in results]