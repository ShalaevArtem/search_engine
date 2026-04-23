from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QCheckBox
from PyQt6.QtCore import Qt
from core.auth_manager import auth_manager

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в систему")
        self.setMinimumSize(380, 220)
        self.setStyleSheet("""
            QDialog { background-color: #18191c; color: #e0e0e0; font-size: 12px; }
            QLineEdit { background-color: #2c2f33; border: 1px solid #444; padding: 6px; color: #e0e0e0; border-radius: 4px; }
            QPushButton { background-color: #7289da; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #5f73bc; }
            QLabel.error { color: #ff5555; font-size: 11px; min-height: 16px; }
            QCheckBox { color: #aaa; }
        """)
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Логин")
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("Пароль")
        self.remember_cb = QCheckBox("Запомнить меня (30 дней)")
        self.error_label = QLabel()
        self.error_label.setObjectName("error")
        self.btn_login = QPushButton("Войти")
        layout.addRow("Логин:", self.user_input)
        layout.addRow("Пароль:", self.pass_input)
        layout.addRow(self.remember_cb)
        layout.addRow(self.error_label)
        layout.addRow(self.btn_login)
        self.btn_login.clicked.connect(self.try_login)
        self.pass_input.returnPressed.connect(self.try_login)

    def try_login(self):
        u, p = self.user_input.text().strip(), self.pass_input.text()
        if not u or not p:
            self.error_label.setText("Заполните все поля")
            return
        if auth_manager.create_session_token(u, p, self.remember_cb.isChecked()):
            self.done(QDialog.DialogCode.Accepted)
        else:
            self.error_label.setText("Неверный логин или пароль")
            self.pass_input.clear()