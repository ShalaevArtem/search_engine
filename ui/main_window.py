import sys, os, time
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QProgressBar
)
from PyQt6.QtCore import Qt, QDate
from config import Config
from core.indexer import FileIndexer, logger
from core.searcher import setup_search_parser, search_index, search_time_range, combined_search, search_by_filename
from core.access_control import check_file_access
from core.auth_manager import auth_manager
from ui.threads.index_thread import IndexThread
from ui.dialogs.preview import PreviewDialog

class FileSearchApp(QMainWindow):
    """Главный класс GUI поисковой системы."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поисковая система")
        self.setMinimumSize(800, 500)
        Config.INDEX_DIR.mkdir(exist_ok=True)
        self.ix = FileIndexer.get_index(Config.INDEX_DIR)
        if self.ix.is_empty():
            print("Индекс пуст. Выполните индексацию.")
        self.parser = setup_search_parser(self.ix.schema)
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_index_tab(), "Индексация")
        self.tabs.addTab(self.create_keywords_tab(), "Ключевые слова")
        self.tabs.addTab(self.create_date_tab(), "Дата")
        self.tabs.addTab(self.create_combined_tab(), "Комбинированный")
        self.tabs.addTab(self.create_filename_tab(), "Имя файла")
        main_layout.addWidget(self.tabs)
        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Путь", "Релевантность", "Дата", "Действие"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setStyleSheet("font-size: 11px; padding: 2px;")
        self.results_table.hide()
        main_layout.addWidget(self.results_table)
        self.results_table.cellDoubleClicked.connect(self.open_file_from_result)
        self.setCentralWidget(central_widget)
        self.setStyleSheet(self.dark_stylesheet())
        self.index_thread = None
        self.last_query = ""

    def dark_stylesheet(self):
        return """
        QMainWindow, QWidget { background-color: #18191c; color: #e0e0e0; font-family: 'Segoe UI', 'Arial', sans-serif; font-size: 11px; }
        QTabWidget::pane { border: 1px solid #23272a; background-color: #23272a; border-radius: 6px; }
        QTabBar::tab { background-color: #23272a; padding: 4px 10px; margin: 1px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-size: 11px; }
        QTabBar::tab:selected { background-color: #2c2f33; color: #7289da; border-bottom: 2px solid #7289da; }
        QLineEdit, QDateEdit { background-color: #2c2f33; border: 1px solid #333; padding: 2px; color: #e0e0e0; border-radius: 3px; font-size: 11px; }
        QPushButton { background-color: #7289da; color: white; border: none; padding: 4px 10px; font-size: 11px; border-radius: 3px; }
        QPushButton:hover { background-color: #5f73bc; }
        QTableWidget { background-color: #23272a; alternate-background-color: #252525; gridline-color: #333; color: #e0e0e0; font-size: 11px; }
        QTableWidget::item { padding: 1px; }
        QHeaderView::section { background-color: #2c2f33; padding: 4px; border: 1px solid #333; border-radius: 3px; font-size: 11px; }
        QProgressBar { border: 1px solid #333; border-radius: 4px; text-align: center; color: #e0e0e0; background-color: #2c2f33; height: 14px; font-size: 11px; }
        QProgressBar::chunk { background-color: #7289da; border-radius: 4px; }
        """

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

        roles = self._get_user_roles()
        self.index_thread = IndexThread(dir_path, roles)
        self.index_thread.progress.connect(self.progress_bar.setValue)
        self.index_thread.finished.connect(self.on_indexing_finished)
        self.index_thread.start()

    def on_indexing_finished(self, success, failed, message):
        self.progress_bar.hide()
        self.tabs.setEnabled(True)

        # Показываем диалог
        QMessageBox.information(self, "Индексация", f"{message}\nПроиндексировано: {success}\nОшибок чтения: {failed}")

        # Отложенное обновление индекса (предотвращает краш 0xC0000409)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self._reload_index_safely)

    def _reload_index_safely(self):
        try:
            self.ix = FileIndexer.get_index(Config.INDEX_DIR)
            self.parser = setup_search_parser(self.ix.schema)
        except Exception as e:
            logger.error(f"Ошибка перезагрузки индекса: {e}")

    def _get_user_roles(self):
        user = auth_manager.get_current_user()
        return user.roles if user and user.roles else []

    def display_results(self, results):
        start_time = time.time()
        self.results_table.setRowCount(0)
        if not results:
            self.results_table.hide()
            QMessageBox.information(self, "Поиск", "Ничего не найдено или нет прав доступа.")
            time.sleep(0.3)
            return
        try:
            for i, res in enumerate(results):
                self.results_table.insertRow(i)
                path = str(res.get('path', ''))
                score = float(res.get('score', 0.0))
                date = str(res.get('last_modified', ''))
                self.results_table.setItem(i, 0, QTableWidgetItem(path))
                self.results_table.setItem(i, 1, QTableWidgetItem(f"{score:.2f}"))
                self.results_table.setItem(i, 2, QTableWidgetItem(date))
                btn = QPushButton("Просмотр")
                btn.setFixedWidth(80)
                btn.setStyleSheet("QPushButton { background-color: #7289da; color: white; border-radius: 3px; }")
                terms = res.get('matched_terms', [])
                btn.clicked.connect(lambda checked=False, p=path, t=terms: PreviewDialog(p, t, self).exec())
                self.results_table.setCellWidget(i, 3, btn)
            self.results_table.show()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка отображения", f"Не удалось показать результаты:\n{e}")
            self.results_table.hide()

    def search_keywords(self):
        self.last_query = self.keywords_input.text()
        if not self.last_query.strip():
            QMessageBox.warning(self, "Внимание", "Введите поисковый запрос!")
            return
        try:
            roles = self._get_user_roles()
            with self.ix.searcher() as searcher:
                res = search_index(searcher, self.parser, self.last_query, user_roles=roles)
            self.display_results(res)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка поиска", str(e))

    def search_date(self):
        try:
            user_roles = self._get_user_roles()
            start = self.start_date.date().toString("yyyy-MM-dd")
            end = self.end_date.date().toString("yyyy-MM-dd")
            with self.ix.searcher() as searcher:
                res = search_time_range(searcher, start, end, user_roles)
            self.display_results(res)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка поиска", str(e))

    def search_combined(self):
        self.last_query = self.combined_query.text()
        if not self.last_query:
            QMessageBox.warning(self, "Внимание", "Введите запрос!")
            return
        try:
            user_roles = self._get_user_roles()
            params = {
                'query': self.last_query,
                'start_date': self.combined_start_date.date().toString("yyyy-MM-dd"),
                'end_date': self.combined_end_date.date().toString("yyyy-MM-dd"),
                'limit': 10
            }
            with self.ix.searcher() as searcher:
                res = combined_search(searcher, self.parser, params, user_roles)
            self.display_results(res)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка поиска", str(e))

    def search_filename(self):
        self.last_query = self.filename_input.text()
        if not self.last_query:
            QMessageBox.warning(self, "Внимание", "Введите имя файла!")
            return
        try:
            user_roles = self._get_user_roles()
            with self.ix.searcher() as searcher:
                res = search_by_filename(searcher, self.last_query, user_roles)
            self.display_results(res)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка поиска", str(e))

    def open_file_from_result(self, row, column):
        path_item = self.results_table.item(row, 0)
        if not path_item:
            return
        path = path_item.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", "Файл не найден!")
            return
        current_user = auth_manager.get_current_user()
        if not current_user or not check_file_access(path, current_user.roles):
            QMessageBox.warning(self, "Отказ в доступе", "У вас нет прав для открытия этого файла.")
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