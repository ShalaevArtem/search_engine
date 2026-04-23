from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QApplication
from PyQt6.QtCore import Qt
from models.database import SessionLocal, User, Role
from core.auth_manager import hash_password

class FirstRunSetupDialog(QDialog):
    """Безопасное окно первой настройки"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Первая настройка системы")
        self.setMinimumSize(420, 210)
        self.setStyleSheet("QDialog { background-color: #18191c; color: #e0e0e0; }")
        layout = QFormLayout(self)
        self.user_in = QLineEdit()
        self.pass_in = QLineEdit()
        self.pass_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn = QPushButton("Создать администратора")
        self.error_lbl = QLabel()
        self.error_lbl.setStyleSheet("color: #ff5555; font-size: 11px;")
        layout.addRow("Логин (≥3 символов):", self.user_in)
        layout.addRow("Пароль (≥6 символов):", self.pass_in)
        layout.addRow(self.error_lbl)
        layout.addRow(self.btn)
        self.btn.clicked.connect(self._save_admin)
        self.pass_in.returnPressed.connect(self._save_admin)

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