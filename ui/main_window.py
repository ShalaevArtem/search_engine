import sys
import os
import time
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QDateEdit, QCheckBox,
    QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QFrame, QStackedWidget, QMessageBox,
    QFileDialog, QStatusBar
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont

from config import Config
from core.indexer import FileIndexer
from core.searcher import (
    setup_search_parser, search_index, search_time_range,
    combined_search, search_by_filename
)
from core.access_control import check_file_access
from core.auth_manager import auth_manager
from ui.threads.index_thread import IndexThread
from ui.dialogs.preview import PreviewDialog

logger = logging.getLogger(__name__)

class FileSearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Поисковая система")
        self.setMinimumSize(1200, 700)

        font = QFont("Segoe UI", 10)
        self.setFont(font)

        Config.INDEX_DIR.mkdir(exist_ok=True)
        self.ix = FileIndexer.get_index(Config.INDEX_DIR)
        if self.ix.is_empty():
            logger.info("Индекс пуст. Выполните индексирование.")
        self.parser = setup_search_parser(self.ix.schema)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_user_panel())
        main_layout.addWidget(self._create_search_panel())

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.hide()
        main_layout.addWidget(self._progress_bar)

        self._results_stack = QStackedWidget()
        self._results_stack.addWidget(self._create_empty_state())
        self._results_stack.addWidget(self._create_results_table())
        self._results_stack.setCurrentIndex(0)
        main_layout.addWidget(self._results_stack, 1)

        self._status_bar = QStatusBar()
        self._status_bar.setFixedHeight(24)
        self._status_bar.showMessage("Готово")
        main_layout.addWidget(self._status_bar)

        self.setStyleSheet(self._system_stylesheet())

        self.index_thread = None

        if self.ix.is_empty():
            self._status_bar.showMessage("Индекс пуст. Обратитесь к администратору для индексирования.")

        self._on_logout_callback = None

    def _create_user_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedHeight(40)
        panel.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-bottom: 1px solid #3E3E42;
            }
            QLabel {
                color: #D4D4D4;
                font-size: 12px;
            }
            QPushButton {
                border: none;
                background: transparent;
                color: #9CDCFE;
                font-size: 12px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #4FC1FF;
                text-decoration: underline;
            }
        """)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        user = auth_manager.get_current_user()
        username = user.username if user else "?"
        self._user_label = QLabel(f"Вы вошли как: <b>{username}</b>")
        layout.addWidget(self._user_label)
        layout.addStretch()

        if user and "admin" in user.roles:
            for label, callback in [
                ("Индексирование", self._show_index_dialog),
                ("Пользователи", self._show_users_dialog),
                ("Доступ", self._show_acl_dialog),
            ]:
                btn = QPushButton(label)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(callback)
                layout.addWidget(btn)

            sep = QLabel("|")
            sep.setStyleSheet("color: #D1D5DB;")
            layout.addWidget(sep)

        logout_btn = QPushButton("Выйти")
        logout_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                color: #6B7280;
                font-size: 12px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #DC2626;
                text-decoration: underline;
            }
        """)
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self._do_logout)
        layout.addWidget(logout_btn)

        return panel

    def _create_search_panel(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3E3E42;
                border-radius: 6px;
            }
            QLabel {
                color: #D4D4D4;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3C3C3C;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 8px;
                color: #D4D4D4;
                font-size: 13px;
                min-height: 28px;
            }
            QLineEdit:focus {
                border: 1px solid #0E639C;
            }
            QPushButton#primary {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 13px;
                min-height: 32px;
            }
            QPushButton#primary:hover {
                background-color: #1177BB;
            }
            QPushButton#primary:pressed {
                background-color: #094771;
            }
            QPushButton#secondary {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
                min-height: 32px;
            }
            QPushButton#secondary:enabled:hover {
                background-color: #4C4C4C;
            }
            QPushButton#secondary:disabled {
                background-color: #2D2D30;
                color: #6E6E6E;
            }
            QRadioButton {
                color: #D4D4D4;
                font-size: 12px;
            }
            QCheckBox {
                color: #D4D4D4;
                font-size: 12px;
            }
            QDateEdit {
                background-color: #3C3C3C;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 8px;
                color: #D4D4D4;
                font-size: 12px;
                min-height: 28px;
            }
            QDateEdit:disabled {
                background-color: #2D2D30;
                color: #6E6E6E;
            }
            QDateEdit::drop-down {
                border-left: 1px solid #3E3E42;
                width: 24px;
            }
            QCalendarWidget {
                background-color: #252526;
            }
            QCalendarWidget QTableView {
                background-color: #252526;
                color: #D4D4D4;
                selection-background-color: #0E639C;
                selection-color: #FFFFFF;
                gridline-color: #3E3E42;
            }
            QCalendarWidget QTableView::item {
                color: #D4D4D4;
                padding: 4px;
            }
            QCalendarWidget QTableView::item:selected {
                background-color: #0E639C;
                color: #FFFFFF;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: #2D2D30;
            }
            QCalendarWidget QToolButton {
                color: #D4D4D4;
                background-color: transparent;
                font-size: 13px;
                padding: 4px;
            }
            QCalendarWidget QSpinBox {
                color: #D4D4D4;
                background-color: #3C3C3C;
                border: 1px solid #3E3E42;
                padding: 2px;
            }
            QCalendarWidget QSpinBox::up-button, QCalendarWidget QSpinBox::down-button {
                background-color: #3E3E42;
                border: 1px solid #3E3E42;
            }
            QCalendarWidget QSpinBox::up-button:hover, QCalendarWidget QSpinBox::down-button:hover {
                background-color: #4C4C4C;
            }
            QCalendarWidget QTableView::item:disabled {
                color: #F85149;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        query_label = QLabel("Запрос:")
        query_label.setFixedWidth(52)
        query_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(query_label)

        self._query_input = QLineEdit()
        self._query_input.setPlaceholderText("Например: отчёт по проекту")
        self._query_input.setMinimumWidth(300)
        row1.addWidget(self._query_input, 1)

        self._search_btn = QPushButton("Поиск")
        self._search_btn.setObjectName("primary")
        self._search_btn.setFixedWidth(100)
        self._search_btn.clicked.connect(self.do_search)
        row1.addWidget(self._search_btn)

        layout.addLayout(row1)

        hint = QLabel("Оставьте поле пустым и включите фильтр по дате, чтобы найти все документы за период")
        hint.setStyleSheet("color: #9CA3AF; font-size: 11px; margin-top: 4px;")
        layout.addWidget(hint)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.setContentsMargins(0, 10, 0, 0)

        scope_label = QLabel("Искать:")
        row2.addWidget(scope_label)

        self._scope_group = QButtonGroup(self)
        for text, id_ in [("Только в именах файлов", 1), ("Только в содержимом", 2)]:
            rb = QRadioButton(text)
            rb.setChecked(id_ == 2)
            self._scope_group.addButton(rb, id_)
            row2.addWidget(rb)

        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.setContentsMargins(0, 8, 0, 0)

        self._date_check = QCheckBox("Ограничить периодом")
        self._date_check.stateChanged.connect(self._on_date_check_changed)
        row3.addWidget(self._date_check)

        self._date_from_label = QLabel("С:")
        self._date_from_label.setEnabled(False)
        row3.addWidget(self._date_from_label)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-30))
        self._date_from.setEnabled(False)
        self._date_from.setMinimumWidth(120)
        row3.addWidget(self._date_from)

        self._date_to_label = QLabel("По:")
        self._date_to_label.setEnabled(False)
        row3.addWidget(self._date_to_label)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setEnabled(False)
        self._date_to.setMinimumWidth(120)
        row3.addWidget(self._date_to)

        self._date_error = QLabel("Начальная дата позже конечной")
        self._date_error.setStyleSheet("color: #DC2626; font-size: 11px;")
        self._date_error.hide()
        row3.addWidget(self._date_error)

        row3.addStretch()
        layout.addLayout(row3)

        return card

    def _create_empty_state(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🔍")
        icon.setStyleSheet("font-size: 48px; color: #D1D5DB;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        text1 = QLabel("Введите запрос и нажмите «Поиск»")
        text1.setStyleSheet("font-size: 14px; color: #6B7280; margin-top: 16px;")
        text1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text1)

        text2 = QLabel("Или включите фильтр по дате и нажмите «Показать за период»")
        text2.setStyleSheet("font-size: 12px; color: #9CA3AF; margin-top: 4px;")
        text2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text2)

        return widget

    def _create_results_table(self) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Имя файла", "Путь", "Дата", "Релевантность", "Предпросмотр"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 400)
        table.setColumnWidth(4, 80)

        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #252526;
                alternate-background-color: #2D2D30;
                gridline-color: #3E3E42;
                color: #D4D4D4;
                font-size: 13px;
                border: 1px solid #3E3E42;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #3E3E42;
            }
            QHeaderView::section {
                background-color: #2D2D30;
                padding: 6px;
                border: 1px solid #3E3E42;
                font-weight: 600;
                font-size: 12px;
                color: #D4D4D4;
            }
        """)

        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)

        table.cellDoubleClicked.connect(self.open_file_from_result)
        return table

    def _system_stylesheet(self) -> str:
        return """
        QMainWindow {
            background-color: #1E1E1E;
        }
        QStatusBar {
            background-color: #252526;
            color: #D4D4D4;
            font-size: 11px;
        }
        QProgressBar {
            border: 1px solid #3E3E42;
            border-radius: 4px;
            text-align: center;
            color: #D4D4D4;
            background-color: #252526;
            height: 18px;
            font-size: 12px;
        }
        QProgressBar::chunk {
            background-color: #0E639C;
            border-radius: 3px;
        }
        QMessageBox {
            background-color: #1E1E1E;
            color: #D4D4D4;
        }
        QMessageBox QPushButton {
            min-width: 80px;
        }
        """

    def _on_date_check_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self._date_from.setEnabled(enabled)
        self._date_from_label.setEnabled(enabled)
        self._date_to.setEnabled(enabled)
        self._date_to_label.setEnabled(enabled)
        self._date_error.hide()

    def _validate_dates(self) -> bool:
        if not self._date_check.isChecked():
            return True

        d_from = self._date_from.date()
        d_to = self._date_to.date()

        if d_from > d_to:
            self._date_from.setStyleSheet("border: 1px solid #DC2626; border-radius: 4px; padding: 4px 8px;")
            self._date_to.setStyleSheet("border: 1px solid #DC2626; border-radius: 4px; padding: 4px 8px;")
            self._date_error.show()
            return False
        else:
            self._date_from.setStyleSheet("")
            self._date_to.setStyleSheet("")
            self._date_error.hide()
            return True

    def do_search(self):
        """Основной поиск: текст + опционально даты."""
        query_text = self._query_input.text().strip()
        scope = self._scope_group.checkedId()
        use_date = self._date_check.isChecked()

        if not query_text and not use_date:
            QMessageBox.warning(self, "Внимание", "Введите запрос или включите фильтр по дате.")
            return

        if use_date and not self._validate_dates():
            return

        roles = self._get_user_roles()
        if not roles:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить роли пользователя.")
            return

        self._status_bar.showMessage("Поиск...")
        t0 = time.perf_counter()

        try:
            with self.ix.searcher() as searcher:
                if use_date and query_text:
                    params = {
                        'query': query_text,
                        'start_date': self._date_from.date().toString("yyyy-MM-dd"),
                        'end_date': self._date_to.date().toString("yyyy-MM-dd"),
                        'limit': 50
                    }
                    results = combined_search(searcher, self.parser, params, roles)

                elif use_date and not query_text:
                    start = self._date_from.date().toString("yyyy-MM-dd")
                    end = self._date_to.date().toString("yyyy-MM-dd")
                    results = search_time_range(searcher, start, end, roles, limit=50)

                elif scope == 1:
                    results = search_by_filename(searcher, query_text, roles, limit=50)

                else:
                    results = search_index(searcher, self.parser, query_text, roles, limit=50)

            elapsed = time.perf_counter() - t0
            self._status_bar.showMessage(f"Найдено: {len(results)} документов | Время: {elapsed:.2f} с")
            self._display_results(results, by_date=False)

        except Exception as e:
            logger.error(f"Ошибка поиска: {e}")
            QMessageBox.critical(self, "Ошибка поиска", str(e))
            self._status_bar.showMessage("Ошибка поиска")

    def do_search_by_period(self):
        """Поиск только по периоду, игнорирует текст."""
        if not self._date_check.isChecked():
            QMessageBox.warning(self, "Внимание", "Включите фильтр по дате.")
            return

        if not self._validate_dates():
            return

        roles = self._get_user_roles()
        if not roles:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить роли пользователя.")
            return

        self._status_bar.showMessage("Поиск за период...")
        t0 = time.perf_counter()

        try:
            start = self._date_from.date().toString("yyyy-MM-dd")
            end = self._date_to.date().toString("yyyy-MM-dd")

            with self.ix.searcher() as searcher:
                results = search_time_range(searcher, start, end, roles, limit=50)

            elapsed = time.perf_counter() - t0
            self._status_bar.showMessage(f"Найдено: {len(results)} документов | Время: {elapsed:.2f} с")
            self._display_results(results, by_date=True)

        except Exception as e:
            logger.error(f"Ошибка поиска по дате: {e}")
            QMessageBox.critical(self, "Ошибка поиска", str(e))
            self._status_bar.showMessage("Ошибка поиска")

    def _display_results(self, results, by_date=False):
        table = self._results_stack.widget(1)

        if not results:
            self._results_stack.setCurrentIndex(0)
            QMessageBox.information(self, "Поиск", "Ничего не найдено.")
            return

        self._results_stack.setCurrentIndex(1)
        table.setRowCount(0)

        scores = [float(r.get('score', 0.0)) for r in results]
        max_score = max(scores) if scores else 1.0
        if max_score == 0:
            max_score = 1.0

        for i, res in enumerate(results):
            table.insertRow(i)

            path = str(res.get('path', ''))
            filename = Path(path).name
            score = float(res.get('score', 0.0))
            date_str = str(res.get('last_modified', ''))

            name_item = QTableWidgetItem(filename)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            table.setItem(i, 0, name_item)

            path_display = path
            if len(path) > 60:
                path_display = "..." + path[-57:]

            path_item = QTableWidgetItem(path_display)
            path_item.setToolTip(path)
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(i, 1, path_item)

            table.setItem(i, 2, QTableWidgetItem(date_str))

            if by_date:
                rel_item = QTableWidgetItem("—")
            else:
                percentage = min(100.0, (score / max_score) * 100.0)
                rel_text = f"{percentage:.0f}%"
                rel_item = QTableWidgetItem(rel_text)

                if percentage >= 80:
                    rel_item.setForeground(Qt.GlobalColor.darkGreen)
                elif percentage >= 50:
                    rel_item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    rel_item.setForeground(Qt.GlobalColor.gray)

            table.setItem(i, 3, rel_item)

            btn = QPushButton("👁")
            btn.setFixedSize(28, 28)
            btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                    color: #005A9E;
                    font-size: 14px;
                }
                QPushButton:hover {
                    color: #004578;
                }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            terms = res.get('matched_terms', [])
            btn.clicked.connect(lambda checked=False, p=path, t=terms: PreviewDialog(p, t, self).exec())
            table.setCellWidget(i, 4, btn)

    def _show_index_dialog(self):
        """Диалог индексирования для администратора."""
        user = auth_manager.get_current_user()
        if not user or "admin" not in user.roles:
            QMessageBox.critical(self, "Отказ в доступе", "Индексирование доступно только администраторам.")
            return

        directory = QFileDialog.getExistingDirectory(self, "Выберите директорию для индексирования")
        if not directory:
            return

        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            QMessageBox.warning(self, "Ошибка", "Указанный путь не существует.")
            return

        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._search_btn.setEnabled(False)

        roles = self._get_user_roles()
        self.index_thread = IndexThread(dir_path, roles)
        self.index_thread.progress.connect(self._progress_bar.setValue)
        self.index_thread.finished.connect(self._on_indexing_finished)
        self.index_thread.start()

    def _on_indexing_finished(self, success, failed, message):
        self._progress_bar.hide()
        self._search_btn.setEnabled(True)

        QMessageBox.information(self, "Индексирование", f"{message}\nПроиндексировано: {success}\nОшибок чтения: {failed}")

        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self._reload_index_safely)

    def _reload_index_safely(self):
        try:
            self.ix = FileIndexer.get_index(Config.INDEX_DIR)
            self.parser = setup_search_parser(self.ix.schema)
            self._status_bar.showMessage("Индекс обновлён")
        except Exception as e:
            logger.error(f"Ошибка перезагрузки индекса: {e}")
            self._status_bar.showMessage("Ошибка обновления индекса")

    def open_file_from_result(self, row, column):
        table = self._results_stack.widget(1)
        name_item = table.item(row, 0)
        if not name_item:
            return

        path = name_item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
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

    def _show_users_dialog(self):
        from ui.dialogs.user_management import UserManagementDialog
        UserManagementDialog(self).exec()

    def _show_acl_dialog(self):
        from ui.dialogs.acl_management import ACLManagementDialog
        ACLManagementDialog(self).exec()

    def _do_logout(self):
        if hasattr(self, "logout_callback"):
            self.logout_callback()

    def _get_user_roles(self):
        user = auth_manager.get_current_user()
        return user.roles if user and user.roles else []