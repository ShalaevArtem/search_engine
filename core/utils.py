import nltk
from colorama import Fore, Style
from nltk.corpus import wordnet as wn, stopwords
from nltk.tokenize import word_tokenize

def setup_nltk():
    """Инициализация ресурсов NLTK"""
    try:
        # Проверяем, загружен ли wordnet
        wn.synsets('example')
    except LookupError:
        nltk.download('wordnet')

    try:
        # Проверяем, загружены ли stopwords
        stopwords.words('english')
    except LookupError:
        nltk.download('stopwords')

    try:
        # Проверяем, загружен ли punkt
        word_tokenize("example")
    except LookupError:
        nltk.download('punkt')

def print_success(message: str):
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

def print_error(message: str):
    print(f"{Fore.RED}{message}{Style.RESET_ALL}")