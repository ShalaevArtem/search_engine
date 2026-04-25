import logging
import re
import string
from datetime import datetime, time, date, timedelta
from functools import lru_cache
from typing import List, Dict, Any, Optional

import nltk
import pymorphy3
from ru_synonyms import SynonymsGraph
from razdel import tokenize

from whoosh.qparser import QueryParser, FuzzyTermPlugin, OrGroup
from whoosh.query import Term, And, Or, DateRange, FuzzyTerm, Prefix
from whoosh.searching import Searcher
from whoosh import index

from config import Config
from models.schemas import SearchResult

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация инструментов для русского языка
morph = pymorphy3.MorphAnalyzer()
sg = SynonymsGraph()

# Локальная папка для NLTK данных
nltk_data_dir = Config.NLTK_DATA_DIR
if nltk_data_dir and nltk_data_dir.exists() and str(nltk_data_dir) not in nltk.data.path:
    nltk.data.path.append(str(nltk_data_dir))

def _format_search_result(hit: Any) -> Dict[str, Any]:
    """
    Безопасно форматирует результат Whoosh в словарь для UI.
    Устраняет дублирование кода и корректно обрабатывает matched_terms.
    """
    matched_terms = []
    try:
        raw_terms = hit.matched_terms()
        matched_terms = list(set(
            t[1].decode('utf-8') if isinstance(t[1], bytes) else str(t[1])
            for t in raw_terms
            if t[0] == 'content'
        ))
    except Exception as e:
        logger.debug(f"Не удалось извлечь matched_terms: {e}")

    return {
        'path': hit['path'],
        'score': hit.score,
        'last_modified': hit.get('last_modified'),
        'matched_terms': matched_terms
    }

def validate_query(query: str) -> tuple[bool, str]:
    """Проверяет длину и наличие опасных символов."""
    if not query or not query.strip():
        return False, "Запрос пустой"
    if len(query) > Config.MAX_QUERY_LENGTH:
        return False, f"Запрос слишком длинный (макс {Config.MAX_QUERY_LENGTH} символов)"
    return True, ""

def lemmatize_ru(word: str) -> str:
    """Лемматизация русского слова через pymorphy3."""
    if not word or word.strip() in string.punctuation:
        return word
    p = morph.parse(word)[0]
    return p.normal_form

def detect_language(word: str) -> str:
    """Определяет язык слова: 'ru' для русского, 'en' для английского."""
    if re.fullmatch(r'[а-яёА-ЯЁ-]+', word):
        return 'ru'
    elif re.fullmatch(r'[a-zA-Z-]+', word):
        return 'en'
    return 'unknown'

@lru_cache(maxsize=Config.MAX_CACHE_SIZE)
def get_synonyms(word: str) -> List[str]:
    """Получает список синонимов для слова (русский и английский)."""
    lang = detect_language(word)

    if lang == 'ru':
        lemma = lemmatize_ru(word)
        if sg.is_in_dictionary(lemma):
            synonyms = list(sg.get_list(lemma))
            return synonyms if synonyms else [lemma]
        return [lemma]
    elif lang == 'en':
        from nltk.corpus import wordnet as wn
        synonyms = set()
        for syn in wn.synsets(word):
            for lemma in syn.lemmas():
                synonyms.add(lemma.name().replace('_', ' '))
        return list(synonyms) if synonyms else [word]
    return [word]

def setup_search_parser(schema):
    """Создаёт и настраивает парсер Whoosh для поиска по содержимому."""
    parser = QueryParser("content", schema, group=OrGroup)
    parser.add_plugin(FuzzyTermPlugin())
    return parser

def tokenize_ru(text: str) -> List[str]:
    """Токенизация русского текста с помощью razdel."""
    return [t.text for t in tokenize(text)]

def tokenize_en(text: str) -> List[str]:
    """Токенизация английского текста с сохранением апострофов."""
    return re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())

def tokenize_text(text: str, lang: str) -> List[str]:
    """Токенизация текста в зависимости от языка."""
    if lang == 'ru':
        return [token.lower() for token in tokenize_ru(text)]
    elif lang == 'en':
        return tokenize_en(text)
    return text.lower().split()


def search_index(
        searcher: Searcher,
        parser: QueryParser,
        query_str: str,
        user_roles: list[str],
        limit: int = 10,
        stop_words: Optional[set] = None
) -> List[Dict[str, Any]]:
    """Поиск по ключевым словам с расширением через синонимы и фильтрацией по ролям."""
    if stop_words is None:
        stop_words = set()
    if not user_roles:
        return []

    logger.info(f"Поиск: '{query_str}' | Роли: {user_roles}")

    # 1. Прямой поиск
    try:
        query = parser.parse(query_str)

        if "admin" not in user_roles:
            role_filter = Or([Term("roles", role) for role in user_roles])
            final_query = And([query, role_filter])
        else:
            final_query = query

        results = searcher.search(final_query, limit=limit, terms=True)
        if results:
            logger.info(f"Прямой поиск: найдено {len(results)} документов")
            return [_format_search_result(hit) for hit in results]
    except Exception as e:
        logger.error(f"Ошибка при прямом поиске: {e}")

    # 2. Поиск с расширением (синонимы + бустинг) + ФИЛЬТР ПО РОЛЯМ
    try:
        lang = detect_language(query_str)
        tokens = tokenize_text(query_str, lang)
        words = [w.lower() for w in tokens if w not in stop_words and w not in string.punctuation]
        logger.debug(f"Токены: {words}")

        synonym_queries = []
        for word in words:
            synonyms = get_synonyms(word)
            logger.debug(f"Синонимы для '{word}': {synonyms[:Config.MAX_SYNONYMS]}")
            if synonyms:
                synonym_queries.append(Or([Term("content", s) for s in synonyms[:Config.MAX_SYNONYMS]]))

        if synonym_queries:
            synonym_expansion = Or(synonym_queries)
            synonym_expansion.boost = 0.6

            original_query = parser.parse(query_str)
            original_query.boost = 2.0

            text_query = Or([original_query, synonym_expansion])

            if "admin" not in user_roles:
                role_filter = Or([Term("roles", role) for role in user_roles])
                final_query = And([text_query, role_filter])
            else:
                final_query = text_query

            results = searcher.search(final_query, limit=limit, terms=True)
            if results:
                logger.info(f"Поиск с расширением: найдено {len(results)} документов")
                return [_format_search_result(hit) for hit in results]

        logger.info("Ничего не найдено")
        return []
    except Exception as e:
        logger.error(f"Ошибка при поиске с синонимами: {e}")
        return []

def search_time_range(
        searcher: Searcher,
        start_date_str: str,
        end_date_str: str,
        user_roles: list[str],
        limit: int = 10
) -> List[Dict[str, Any]]:
    """Поиск документов по временному диапазону с фильтрацией по ролям."""
    if not user_roles:
        return []

    try:
        start_date = None
        end_date = None

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

        if start_date and end_date:
            start_dt = datetime.combine(start_date, time.min)
            end_dt = datetime.combine(end_date, time.max)
            date_query = DateRange("last_modified", start_dt, end_dt)
        elif start_date:
            start_dt = datetime.combine(start_date, time.min)
            date_query = DateRange("last_modified", start_dt, datetime.max)
        elif end_date:
            end_dt = datetime.combine(end_date, time.max)
            date_query = DateRange("last_modified", datetime.min, end_dt)
        else:
            return []

        if "admin" not in user_roles:
            role_filter = Or([Term("roles", role) for role in user_roles])
            final_query = And([date_query, role_filter])
        else:
            final_query = date_query

        results = searcher.search(final_query, limit=limit)
        return [_format_search_result(hit) for hit in results]

    except ValueError as e:
        logger.error(f"Неверный формат даты: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка поиска по дате: {e}")
        return []


def combined_search(
        searcher: Searcher,
        parser: QueryParser,
        params: Dict[str, Any],
        user_roles: list[str],
        stop_words: Optional[set] = None
) -> List[Dict[str, Any]]:
    """Комбинированный поиск: текст + диапазон дат + фильтрация по ролям."""
    if stop_words is None:
        stop_words = set()
    if not user_roles:
        return []

    query_str = params.get('query', '')
    start_date_str = params.get('start_date')
    end_date_str = params.get('end_date')
    limit = params.get('limit', 10)

    logger.info(f"Комбо-поиск: '{query_str}' | Даты: {start_date_str} -> {end_date_str} | Роли: {user_roles}")

    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        date_query = DateRange(
            "last_modified",
            datetime.combine(start_dt, time.min),
            datetime.combine(end_dt, time.max)
        )

        # Прямой поиск + дата + роли
        original_query = parser.parse(query_str)
        direct_query = And([original_query, date_query])

        if "admin" not in user_roles:
            role_filter = Or([Term("roles", role) for role in user_roles])
            direct_query = And([direct_query, role_filter])

        results = searcher.search(direct_query, limit=limit, terms=True)
        if results:
            logger.info(f"Прямой комбо: найдено {len(results)} документов")
            return [_format_search_result(hit) for hit in results]

        # Поиск с синонимами + дата + роли
        lang = detect_language(query_str)
        tokens = tokenize_text(query_str, lang)
        words = [w.lower() for w in tokens if w not in stop_words and w not in string.punctuation]

        synonym_queries = []
        for word in words:
            synonyms = get_synonyms(word)
            if synonyms:
                synonym_queries.append(Or([Term("content", s) for s in synonyms[:Config.MAX_SYNONYMS]]))

        if synonym_queries:
            synonym_expansion = Or(synonym_queries)
            synonym_expansion.boost = 0.6

            original_boosted = parser.parse(query_str)
            original_boosted.boost = 2.0

            text_query = Or([original_boosted, synonym_expansion])
            combined_query = And([text_query, date_query])

            if "admin" not in user_roles:
                role_filter = Or([Term("roles", role) for role in user_roles])
                combined_query = And([combined_query, role_filter])

            results = searcher.search(combined_query, limit=limit, terms=True)
            if results:
                logger.info(f"Комбо по синонимам: найдено {len(results)} документов")
                return [_format_search_result(hit) for hit in results]

        logger.info("Комбо-поиск не дал результатов")
        return []

    except Exception as e:
        logger.error(f"Ошибка в combined_search: {e}")
        return []


def search_by_filename(
        searcher: Searcher,
        filename: str,
        user_roles: list[str],
        limit: int = 10
) -> List[Dict[str, Any]]:
    """Оптимизированный поиск по имени файла с фильтрацией по ролям."""
    if not filename or not filename.strip() or not user_roles:
        return []

    query_str = filename.strip().lower()

    try:
        q1 = Prefix("filename", query_str).boost(2.0)
        q2 = Term("filename", query_str).boost(3.0)
        q3 = FuzzyTerm("filename", query_str, maxdist=1).boost(0.5)

        query = Or([q1, q2, q3])

        if "admin" not in user_roles:
            role_filter = Or([Term("roles", role) for role in user_roles])
            final_query = And([query, role_filter])
        else:
            final_query = query

        results = searcher.search(final_query, limit=limit)

        if results:
            logger.info(f"Поиск по имени: найдено {len(results)} документов")
            return [_format_search_result(hit) for hit in results]
        return []
    except Exception as e:
        logger.error(f"Ошибка поиска по имени файла: {e}")
        return []