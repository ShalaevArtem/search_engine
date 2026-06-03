import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton, QHBoxLayout
from PyQt6.QtCore import QTimer
from models.database import init_db, DB_PATH, engine
from core.auth_manager import auth_manager
from ui.main_window import FileSearchApp
from ui.dialogs.login import LoginDialog
from ui.dialogs.user_management import UserManagementDialog
from ui.dialogs.acl_management import ACLManagementDialog
from ui.dialogs.setup import FirstRunSetupDialog

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    is_ready = init_db()
    if not is_ready and DB_PATH.exists():
        logger.warning("База данных существует, но пуста или повреждена. Пересоздаём...")
        engine.dispose()
        import time
        time.sleep(0.15)
        try:
            DB_PATH.unlink(missing_ok=True)
            for ext in ('-wal', '-shm'):
                p = DB_PATH.with_suffix(f'.db{ext}')
                if p.exists():
                    p.unlink()
        except PermissionError as e:
            logger.error(f"Не удалось удалить базу данных: {e}.")
            sys.exit(1)
        is_ready = init_db()

    if not is_ready:
        setup_dlg = FirstRunSetupDialog()
        if setup_dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    active_window = None

    def show_login():
        global active_window
        if auth_manager.check_stored_session():
            show_main_window()
            return
        active_window = LoginDialog()
        active_window.rejected.connect(app.quit)
        active_window.accepted.connect(show_main_window)
        active_window.show()

    def show_main_window():
        global active_window
        active_window = FileSearchApp()
        def handle_close_event(event):
            if event.spontaneous():
                app.quit()
            event.accept()
        active_window.closeEvent = handle_close_event
        main_layout = active_window.centralWidget().layout()
        if main_layout:
            btns_layout = QHBoxLayout()
            btns_layout.setSpacing(8)
            if auth_manager.has_role("admin"):
                for btn_cls, label in [(UserManagementDialog, "Пользователи"), (ACLManagementDialog, "Доступ")]:
                    btn = QPushButton(label)
                    btn.setStyleSheet("QPushButton { background-color: #f04747; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; }")
                    btn.clicked.connect(lambda checked=False, cls=btn_cls: cls(active_window).exec())
                    btns_layout.addWidget(btn)
            logout_btn = QPushButton("Выйти")
            logout_btn.setStyleSheet("QPushButton { background-color: #43b581; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; }")
            def on_logout():
                auth_manager.clear_session()
                active_window.close()
                QTimer.singleShot(100, show_login)
            logout_btn.clicked.connect(on_logout)
            btns_layout.addWidget(logout_btn)
            main_layout.addLayout(btns_layout)
        active_window.show()

    show_login()
    sys.exit(app.exec())