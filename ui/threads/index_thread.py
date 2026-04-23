from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from core.indexer import FileIndexer

class IndexThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, int, str)

    def __init__(self, directory: Path, user_roles: list[str]):
        super().__init__()
        self.directory = directory
        self.user_roles = user_roles

    def run(self):
        def progress_callback(value):
            self.progress.emit(value)
        try:
            success, failed = FileIndexer.index_files(self.directory, self.user_roles, progress_callback)
            self.finished.emit(success, failed, "Индексация завершена")
        except Exception as e:
            self.finished.emit(0, 0, f"Ошибка: {str(e)}")