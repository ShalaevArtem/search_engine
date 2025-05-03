import subprocess
import sys
import os
import pathlib

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.environ["PYMORPHY2_DICT_PATH"] = str(pathlib.Path(sys._MEIPASS).joinpath('pymorphy2_dicts_ru/data'))
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    os.environ["PYCHARTS_GALLERY_API"] = str(pathlib.Path(sys._MEIPASS).joinpath('ru-synonyms'))

import ru_synonyms
import pymorphy2_dicts_ru
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QProgressBar, QDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal

# Модули поиска и индексации
from core.indexer import FileIndexer
from core.searcher import (
    setup_search_parser, search_index, search_time_range,
    combined_search, search_by_filename
)
from config import Config

class IndexThread(QThread):
    """Поток для индексации с прогресс-баром"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, int, str)  # success, failed, message

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def run(self):
        def progress_callback(value):
            self.progress.emit(value)
        try:
            success, failed = FileIndexer.index_files(self.directory, progress_callback)
            self.finished.emit(success, failed, "Индексация завершена")
        except Exception as e:
            self.finished.emit(0, 0, f"Ошибка: {str(e)}")

class ModernSearchApp(QMainWindow):
    """Основной класс GUI"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поисковая система")
        self.setMinimumSize(800, 500)

        # Индекс и парсер
        Config.INDEX_DIR.mkdir(exist_ok=True)
        self.ix = FileIndexer.get_index(Config.INDEX_DIR)
        if self.ix.is_empty():
            print("Индекс пуст. Выполните индексацию.")
        self.parser = setup_search_parser(self.ix.schema)

        # Layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # Прогресс-бар (по умолчанию скрыт)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Вкладки
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_index_tab(), "📁 Индексация")
        self.tabs.addTab(self.create_keywords_tab(), "🔍 Ключевые слова")
        self.tabs.addTab(self.create_date_tab(), "📅 Дата")
        self.tabs.addTab(self.create_combined_tab(), "⚡ Комбинированный")
        self.tabs.addTab(self.create_filename_tab(), "📝 Имя файла")
        main_layout.addWidget(self.tabs)

        # Таблица результатов (по умолчанию скрыта)
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Имя", "Релевантность", "Дата изменения"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setStyleSheet("font-size: 11px; padding: 2px;")
        self.results_table.hide()
        main_layout.addWidget(self.results_table)
        self.results_table.cellDoubleClicked.connect(self.open_file_from_result)

        self.setCentralWidget(central_widget)
        self.setStyleSheet(self.dark_stylesheet())

        self.index_thread = None

    def dark_stylesheet(self):
        return """
        QMainWindow, QWidget {
            background-color: #18191c;
            color: #e0e0e0;
            font-family: 'Segoe UI', 'Arial', sans-serif;
            font-size: 11px;
        }
        QTabWidget::pane {
            border: 1px solid #23272a;
            background-color: #23272a;
            border-radius: 6px;
        }
        QTabBar::tab {
            background-color: #23272a;
            padding: 4px 10px;
            margin: 1px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-size: 11px;
        }
        QTabBar::tab:selected {
            background-color: #2c2f33;
            color: #7289da;
            border-bottom: 2px solid #7289da;
        }
        QLineEdit, QDateEdit {
            background-color: #2c2f33;
            border: 1px solid #333;
            padding: 2px;
            color: #e0e0e0;
            border-radius: 3px;
            font-size: 11px;
        }
        QPushButton {
            background-color: #7289da;
            color: white;
            border: none;
            padding: 4px 10px;
            font-size: 11px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #5f73bc;
        }
        QTableWidget {
            background-color: #23272a;
            alternate-background-color: #252525;
            gridline-color: #333;
            color: #e0e0e0;
            font-size: 11px;
        }
        QTableWidget::item {
            padding: 1px;
        }
        QHeaderView::section {
            background-color: #2c2f33;
            padding: 4px;
            border: 1px solid #333;
            border-radius: 3px;
            font-size: 11px;
        }
        QProgressBar {
            border: 1px solid #333;
            border-radius: 4px;
            text-align: center;
            color: #e0e0e0;
            background-color: #2c2f33;
            height: 14px;
            font-size: 11px;
        }
        QProgressBar::chunk {
            background-color: #7289da;
            border-radius: 4px;
        }
        """

    # --- Вкладки ---
    def create_index_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Путь к папке:"))
        self.dir_input = QLineEdit()
        layout.addWidget(self.dir_input)
        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(self.browse_directory)
        layout.addWidget(browse_btn)
        index_btn = QPushButton("Индексировать")
        index_btn.clicked.connect(self.start_indexing)
        layout.addWidget(index_btn)
        return tab

    def create_keywords_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Запрос:"))
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("Например: отчёт по проекту")
        layout.addWidget(self.keywords_input)
        search_btn = QPushButton("Поиск")
        search_btn.clicked.connect(self.search_keywords)
        layout.addWidget(search_btn)
        return tab

    def create_date_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Начальная дата:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addDays(-30))
        layout.addWidget(self.start_date)
        layout.addWidget(QLabel("Конечная дата:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        layout.addWidget(self.end_date)
        search_btn = QPushButton("Поиск")
        search_btn.clicked.connect(self.search_date)
        layout.addWidget(search_btn)
        return tab

    def create_combined_tab(self):
        tab = QWidget()
        vlayout = QVBoxLayout(tab)
        vlayout.setSpacing(3)
        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(QLabel("Запрос:"))
        self.combined_query = QLineEdit()
        self.combined_query.setPlaceholderText("Ключевые слова...")
        hlayout1.addWidget(self.combined_query)
        vlayout.addLayout(hlayout1)
        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(QLabel("Начальная дата:"))
        self.combined_start_date = QDateEdit()
        self.combined_start_date.setCalendarPopup(True)
        self.combined_start_date.setDate(QDate.currentDate().addDays(-30))
        hlayout2.addWidget(self.combined_start_date)
        hlayout2.addWidget(QLabel("Конечная дата:"))
        self.combined_end_date = QDateEdit()
        self.combined_end_date.setCalendarPopup(True)
        self.combined_end_date.setDate(QDate.currentDate())
        hlayout2.addWidget(self.combined_end_date)
        vlayout.addLayout(hlayout2)
        search_btn = QPushButton("Поиск")
        search_btn.clicked.connect(self.search_combined)
        vlayout.addWidget(search_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return tab

    def create_filename_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Имя файла:"))
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Например: report.docx")
        layout.addWidget(self.filename_input)
        search_btn = QPushButton("Поиск")
        search_btn.clicked.connect(self.search_filename)
        layout.addWidget(search_btn)
        return tab

    # --- Действия ---
    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Выберите директорию")
        if directory:
            self.dir_input.setText(directory)

    def start_indexing(self):
        directory = self.dir_input.text()
        if not directory:
            QMessageBox.warning(self, "Внимание", "Укажите путь к директории!")
            return
        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            QMessageBox.warning(self, "Ошибка", "Указанный путь не существует или не является директорией!")
            return

        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tabs.setEnabled(False)

        self.index_thread = IndexThread(dir_path)
        self.index_thread.progress.connect(self.progress_bar.setValue)
        self.index_thread.finished.connect(self.on_indexing_finished)
        self.index_thread.start()

    def on_indexing_finished(self, success, failed, message):
        self.progress_bar.hide()
        self.tabs.setEnabled(True)
        QMessageBox.information(self, "Индексация", f"{message}\nУспешно: {success}, Ошибок: {failed}")
        # Обновить индекс и парсер после индексации
        self.ix = FileIndexer.get_index(Config.INDEX_DIR)
        self.parser = setup_search_parser(self.ix.schema)

    def display_results(self, results):
        self.results_table.setRowCount(0)
        for i, result in enumerate(results):
            self.results_table.insertRow(i)
            path_item = QTableWidgetItem(result.get('path', ''))
            score_item = QTableWidgetItem(f"{result.get('score', 0):.2f}" if 'score' in result else "")
            date_item = QTableWidgetItem(str(result.get('last_modified', '')))
            self.results_table.setItem(i, 0, path_item)
            self.results_table.setItem(i, 1, score_item)
            self.results_table.setItem(i, 2, date_item)
        self.results_table.show()

    def search_keywords(self):
        query = self.keywords_input.text()
        if not query:
            QMessageBox.warning(self, "Внимание", "Введите поисковый запрос!")
            return
        with self.ix.searcher() as searcher:
            results = search_index(searcher, self.parser, query)
        self.display_results(results)

    def search_date(self):
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        with self.ix.searcher() as searcher:
            results = search_time_range(searcher, start_date, end_date)
        self.display_results(results)

    def search_combined(self):
        query = self.combined_query.text()
        start_date = self.combined_start_date.date().toString("yyyy-MM-dd")
        end_date = self.combined_end_date.date().toString("yyyy-MM-dd")
        params = {
            'query': query,
            'start_date': start_date,
            'end_date': end_date,
            'limit': 10
        }
        with self.ix.searcher() as searcher:
            results = combined_search(searcher, self.parser, params)
        self.display_results(results)

    def search_filename(self):
        filename = self.filename_input.text()
        if not filename:
            QMessageBox.warning(self, "Внимание", "Введите имя файла!")
            return
        with self.ix.searcher() as searcher:
            results = search_by_filename(searcher, filename)
        self.display_results(results)

    def open_file_from_result(self, row, column):
        path_item = self.results_table.item(row, 0)
        if not path_item:
            return
        path = path_item.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", "Файл не найден!")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", path])
            else:
                import subprocess
                subprocess.run(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModernSearchApp()
    window.show()
    sys.exit(app.exec())
