import sys
import logging
from PyQt6.QtWidgets import QApplication, QDialog
from models.database import init_db, DB_PATH, engine
from core.auth_manager import auth_manager
from ui.main_window import FileSearchApp
from ui.dialogs.login import LoginDialog
from ui.dialogs.setup import FirstRunSetupDialog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

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
    logout_requested = False

    def show_login():
        global active_window
        if auth_manager.check_stored_session():
            show_main_window()
            return
        active_window = LoginDialog()

        def login_closed():
            if not logout_requested:
                app.quit()

        active_window.rejected.connect(login_closed)

        active_window.accepted.connect(show_main_window)
        active_window.show()

    def logout():
        global logout_requested
        global active_window

        logout_requested = True

        auth_manager.clear_session()

        if active_window:
            active_window.close()

        logout_requested = False

        show_login()

    def show_main_window():
        global active_window

        active_window = FileSearchApp()
        active_window.logout_callback = logout
        active_window.show()

    show_login()
    sys.exit(app.exec())