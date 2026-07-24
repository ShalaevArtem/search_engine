from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QApplication
from models.database import SessionLocal, User, Role
from core.auth_manager import hash_password

class FirstRunSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Первая настройка системы")
        self.setMinimumSize(420, 240)
        self._apply_dark_theme()

        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.user_in = QLineEdit()
        self.user_in.setPlaceholderText("admin")
        self.pass_in = QLineEdit()
        self.pass_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_in.setPlaceholderText("минимум 6 символов")
        self.btn = QPushButton("Создать администратора")
        self.btn.setObjectName("primary")
        self.error_lbl = QLabel()
        self.error_lbl.setObjectName("error")

        layout.addRow("Логин (≥3 символов):", self.user_in)
        layout.addRow("Пароль (≥6 символов):", self.pass_in)
        layout.addRow(self.error_lbl)
        layout.addRow(self.btn)

        self.btn.clicked.connect(self._save_admin)
        self.pass_in.returnPressed.connect(self._save_admin)

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #D4D4D4;
                font-size: 13px;
            }
            QLabel {
                color: #D4D4D4;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                min-height: 28px;
            }
            QLineEdit:focus {
                border: 1px solid #0E639C;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton#primary {
                background-color: #238636;
            }
            QPushButton#primary:hover {
                background-color: #2EA043;
            }
            QLabel#error {
                color: #F85149;
                font-size: 12px;
            }
        """)

    def _save_admin(self):
        u, p = self.user_in.text().strip(), self.pass_in.text()
        if len(u) < 3 or len(p) < 6:
            self.error_lbl.setText("Логин ≥3, пароль ≥6 символов")
            return
        self.btn.setEnabled(False)
        self.error_lbl.setText("Создание учётной записи...")
        QApplication.processEvents()
        try:
            db = SessionLocal()
            try:
                if db.query(User).first():
                    self.accept()
                    return
                admin_role = Role(name="admin", description="Полный доступ")
                user_role = Role(name="user", description="Стандартный доступ")
                admin_user = User(username=u, password_hash=hash_password(p), is_active=True)
                admin_user.roles.append(admin_role)
                db.add_all([admin_role, user_role, admin_user])
                db.commit()
                self.accept()
            finally:
                db.close()
        except Exception as e:
            self.btn.setEnabled(True)
            self.error_lbl.setText(f"Ошибка: {str(e)[:60]}")