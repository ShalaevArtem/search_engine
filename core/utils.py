import nltk
from colorama import Fore, Style
from nltk.corpus import wordnet as wn, stopwords
from nltk.tokenize import word_tokenize

def setup_nltk():
    """
    Инициализация необходимых ресурсов NLTK.

    Проверяет наличие и при необходимости загружает:
    - словарь WordNet (для работы с синонимами и лемматизацией),
    - стоп-слова (набор часто встречающихся слов, которые можно игнорировать),
    - модель токенизации 'punkt' (для разбиения текста на слова).

    Это позволяет избежать ошибок при первом запуске программы,
    если ресурсы NLTK ещё не загружены.
    """
    try:
        # Попытка получить синонимы для слова 'example' для проверки WordNet
        wn.synsets('example')
    except LookupError:
        nltk.download('wordnet')

    try:
        # Проверка загрузки стоп-слов для английского языка
        stopwords.words('english')
    except LookupError:
        nltk.download('stopwords')

    try:
        # Проверка загрузки модели токенизации 'punkt'
        word_tokenize("example")
    except LookupError:
        nltk.download('punkt')

def print_success(message: str):
    """
    Выводит сообщение в консоль зеленым цветом,
    обозначая успешное выполнение операции.
    """
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

def print_error(message: str):
    """
    Выводит сообщение в консоль красным цветом,
    обозначая ошибку или важное предупреждение.
    """
    print(f"{Fore.RED}{message}{Style.RESET_ALL}")