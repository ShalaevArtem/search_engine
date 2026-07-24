import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QDate

from ui.main_window import FileSearchApp
from core.auth_manager import CurrentUser

app = QApplication.instance() or QApplication([])

class TestDateValidation:
    """Тесты валидации дат в панели поиска."""
    @pytest.fixture
    def window(self):
        """Создаёт FileSearchApp с замоканным индексом."""
        with patch('ui.main_window.FileIndexer.get_index') as mock_ix:
            mock_ix.return_value.is_empty.return_value = False
            mock_ix.return_value.schema = None
            with patch('ui.main_window.setup_search_parser'):
                with patch('core.auth_manager.auth_manager.get_current_user',
                          return_value=CurrentUser(id=1, username="test", roles=["user"])):
                    w = FileSearchApp()
                    yield w
                    w.close()

    def test_validate_dates_ok(self, window):
        """С <= По — валидно."""
        window._date_check.setChecked(True)
        window._date_from.setDate(QDate(2026, 1, 1))
        window._date_to.setDate(QDate(2026, 1, 10))
        assert window._validate_dates() is True
        assert not window._date_error.isVisible()

    def test_validate_dates_invalid(self, window):
        """С > По — невалидно, ошибка видна."""
        window._date_check.setChecked(True)
        window._date_from.setDate(QDate(2026, 1, 10))
        window._date_to.setDate(QDate(2026, 1, 1))

        result = window._validate_dates()

        assert result is False
        assert not window._date_error.isHidden() 

class TestAdminPanelVisibility:
    """Тесты видимости админ-элементов."""
    @pytest.fixture
    def admin_window(self):
        with patch('ui.main_window.FileIndexer.get_index') as mock_ix:
            mock_ix.return_value.is_empty.return_value = False
            mock_ix.return_value.schema = None
            with patch('ui.main_window.setup_search_parser'):
                with patch('core.auth_manager.auth_manager.get_current_user',
                          return_value=CurrentUser(id=1, username="admin", roles=["admin"])):
                    w = FileSearchApp()
                    yield w
                    w.close()

    @pytest.fixture
    def user_window(self):
        with patch('ui.main_window.FileIndexer.get_index') as mock_ix:
            mock_ix.return_value.is_empty.return_value = False
            mock_ix.return_value.schema = None
            with patch('ui.main_window.setup_search_parser'):
                with patch('core.auth_manager.auth_manager.get_current_user',
                          return_value=CurrentUser(id=2, username="user", roles=["user"])):
                    w = FileSearchApp()
                    yield w
                    w.close()

    def test_admin_sees_index_link(self, admin_window):
        """Admin видит ссылку 'Индексирование'."""
        panel = admin_window.centralWidget().layout().itemAt(0).widget()
        layout = panel.layout()
        texts = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and hasattr(w, 'text'):
                texts.append(w.text())
        assert "Индексирование" in texts

    def test_user_no_index_link(self, user_window):
        """User не видит ссылку 'Индексирование'."""
        panel = user_window.centralWidget().layout().itemAt(0).widget()
        layout = panel.layout()
        texts = []
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and hasattr(w, 'text'):
                texts.append(w.text())
        assert "Индексирование" not in texts