from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QCheckBox, QHBoxLayout
from core.auth_manager import auth_manager

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в систему")
        self.setMinimumSize(380, 260)
        self._apply_dark_theme()

        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("ivanov@work.ru")
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("минимум 6 символов")
        self.remember_cb = QCheckBox("Запомнить меня (30 дней)")
        self.error_label = QLabel()
        self.error_label.setObjectName("error")

        layout.addRow("Логин:", self.user_input)
        layout.addRow("Пароль:", self.pass_input)
        layout.addRow(self.remember_cb)
        layout.addRow(self.error_label)

        btn_layout = QHBoxLayout()
        self.btn_login = QPushButton("Войти")
        self.btn_login.setObjectName("primary")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setObjectName("secondary")
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_cancel)
        layout.addRow(btn_layout)

        self.btn_login.clicked.connect(self.try_login)
        self.btn_cancel.clicked.connect(self.reject)
        self.pass_input.returnPressed.connect(self.try_login)

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
            QPushButton#secondary {
                background-color: transparent;
                color: #9CDCFE;
                border: 1px solid #3E3E42;
            }
            QPushButton#secondary:hover {
                background-color: #2D2D30;
                color: #D4D4D4;
            }
            QLabel#error {
                color: #F85149;
                font-size: 12px;
                min-height: 16px;
            }
            QCheckBox {
                color: #D4D4D4;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

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