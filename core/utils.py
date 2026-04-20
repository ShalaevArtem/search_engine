from colorama import Fore, Style

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