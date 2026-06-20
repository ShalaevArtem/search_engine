from colorama import Fore, Style

def print_success(message: str):
    print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

def print_error(message: str):
    print(f"{Fore.RED}{message}{Style.RESET_ALL}")