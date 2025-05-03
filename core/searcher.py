import logging
import re
import string
from datetime import datetime, time, date, timedelta
from functools import lru_cache
from typing import List

from whoosh.analysis import StandardAnalyzer
from whoosh.qparser import QueryParser, FuzzyTermPlugin, OrGroup
from whoosh.query import Term, And, Or, DateRange, FuzzyTerm, Wildcard
from nltk import word_tokenize
from nltk.corpus import wordnet as wn
from natasha import Segmenter, NewsEmbedding, NewsMorphTagger, MorphVocab, Doc
from ru_synonyms import SynonymsGraph
from razdel import tokenize

from config import Config
from models.schemas import SearchResult
from .utils import print_error

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

segmenter = Segmenter()
emb = NewsEmbedding()
morph_tagger = NewsMorphTagger(emb)
morph_vocab = MorphVocab()
sg = SynonymsGraph()

def lemmatize_ru(word):
    doc = Doc(word)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    for token in doc.tokens:
        token.lemmatize(morph_vocab)
    if doc.tokens:
        return doc.tokens[0].lemma
    return word

def detect_language(word: str) -> str:
    if re.fullmatch(r'[а-яёА-ЯЁ-]+', word):
        return 'ru'
    elif re.fullmatch(r'[a-zA-Z-]+', word):
        return 'en'
    return 'unknown'

@lru_cache(maxsize=Config.MAX_CACHE_SIZE)
def get_synonyms(word: str) -> List:
    """Получение синонимов с кэшированием"""
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

def setup_search_parser(schema):
    """Настройка парсера запросов"""
    parser = QueryParser("content", schema, group=OrGroup)
    parser.add_plugin(FuzzyTermPlugin())
    return parser

def tokenize_ru(text: str) -> List[str]: return [t.text for t in tokenize(text)]

def tokenize_text(text: str, lang: str) -> List[str]:
    if lang == 'ru':
        # Используем Natasha или razdel
        return [token.lower() for token in tokenize_ru(text)]
    else:
        # Для английского можно оставить nltk.word_tokenize
        return [token.lower() for token in word_tokenize(text)]

def search_index(searcher, parser, query_str: str, limit: int = 10, stop_words=None) -> List[SearchResult]:
    """Поиск по словам с синонимами"""
    if stop_words is None:
        stop_words = set()

    # Прямой поиск
    try:
        query = parser.parse(query_str)
        results = searcher.search(query, limit=limit)
        if results:
            return [{
                'path': hit['path'],
                'score': hit.score,
                'last_modified': hit.get('last_modified')
            } for hit in results]
    except Exception as e:
        print_error(f"Ошибка при прямом поиске: {e}")
        return []

    # Поиск с синонимами
    try:
        lang = detect_language(query_str)
        tokens = tokenize_text(query_str, lang)

        words = [
            w.lower()
            for w in tokens
            if w not in stop_words and w not in string.punctuation
        ]
        synonym_queries = []
        for word in words:
            synonyms = get_cache_synonyms(word)
            if synonyms:
                term_queries = [Term("content", syn) for syn in synonyms[:Config.MAX_SYNONYMS]]
                synonym_queries.append(Or(term_queries))
        if synonym_queries:
            combined_query = And(synonym_queries)
            results = searcher.search(combined_query, limit=limit)
            return [{
                'path': hit['path'],
                'score': hit.score,
                'last_modified': hit.get('last_modified')
            } for hit in results]
        return []
    except Exception as e:
        print_error(f"Ошибка при поиске с синонимами: {e}")
        return []

def search_time_range(searcher, start_date_str: str, end_date_str: str, limit: int = 10) -> List[SearchResult]:
    """Поиск по временному диапазону"""
    start_date = None
    end_date = None
    try:
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
            # Преобразуем date в datetime для DateRange
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())

            date_query = DateRange("last_modified", start_datetime, end_datetime)  # Используем объекты datetime
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
            hits = searcher.search(date_query, limit=limit)
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

@lru_cache(maxsize=Config.MAX_CACHE_SIZE)
def get_cache_synonyms(word):
    """
    Возвращает список синонимов для слова (русского или английского)
    с кэшированием результата.
    """
    return get_synonyms(word)

def combined_search(searcher, parser, params: dict, stop_words=None) -> List[SearchResult]:
    """
    Комбинированный поиск по временному диапазону
    и словам с синонимами
    """
    if stop_words is None:
        stop_words = set()

    try:
        start_dt = datetime.strptime(params['start_date'], "%Y-%m-%d").date()
        end_dt = datetime.strptime(params['end_date'], "%Y-%m-%d").date()
        text_query = parser.parse(params['query'])
        date_query = DateRange(
            "last_modified",
            datetime.combine(start_dt, time.min),
            datetime.combine(end_dt, time.max)
        )

        # Прямой поиск
        combined_query = And([text_query, date_query])
        results = searcher.search(combined_query, limit=params.get('limit', 10))
        if results:
            return [{
                'path': hit['path'],
                'score': hit.score,
                'last_modified': hit.get('last_modified')
            } for hit in results]

        # Поиск с синонимами
        lang = detect_language(params['query'])
        tokens = tokenize_text(params['query'], lang)

        words = [
            w.lower()
            for w in tokens
            if w not in stop_words and w not in string.punctuation
        ]
        synonym_queries = []
        for word in words:
            synonyms = get_cache_synonyms(word)
            if synonyms:
                term_queries = [Term("content", syn) for syn in synonyms[:Config.MAX_SYNONYMS]]
                synonym_queries.append(Or(term_queries))
        if synonym_queries:
            text_query_synonyms = And(synonym_queries)
            combined_query_synonyms = And([text_query_synonyms, date_query])
            results = searcher.search(combined_query_synonyms, limit=params.get('limit', 10))
            return [{
                'path': hit['path'],
                'score': hit.score,
                'last_modified': hit.get('last_modified')
            } for hit in results]
        else:
            return []
    except Exception as e:
        print_error(f"Ошибка в combined_search: {e}")
        return []

def _normalize_filename(filename):
    """Преобразует имя файла в строку для сравнения."""
    if isinstance(filename, bytes):
        try:
            return filename.decode('utf-8').lower()
        except UnicodeDecodeError:
            return None  # Или другое значение по умолчанию
    elif isinstance(filename, str):
        return filename.lower()
    elif isinstance(filename, int):
        return str(filename).lower()  # Преобразуем число в строку
    else:
        return None  # Пропускаем неизвестные форматы

def search_by_filename(searcher, filename: str) -> List[SearchResult]:
    """Поиск по имени файла с обработкой всех форматов данных"""
    filename_query = filename.lower().strip()

    analyzer = StandardAnalyzer()
    query_parts = [part.text for part in analyzer(filename_query)] # Упрощенный список частей запроса

    queries = []
    for part in query_parts:
        wildcard_query = Wildcard("filename", f"*{part}*")
        fuzzy_query = FuzzyTerm("filename", part, maxdist=2)
        queries.append(Or([wildcard_query, fuzzy_query]))

    if len(queries) > 1:
        query = And(queries)
    else:
        query = queries[0]

    results = searcher.search(query, limit=Config.FILE_SEARCH_LIMIT)

    matched_docs = []
    for hit in results:
        doc_filename = hit['filename']
        doc_str = _normalize_filename(doc_filename)

        if doc_str and (doc_str.startswith(filename_query) or filename_query in doc_str):
            matched_docs.append({
                'path': hit['path'],
                'filename': doc_str,
                'last_modified': hit['last_modified'],
                'score': hit.score
            })
    return matched_docs