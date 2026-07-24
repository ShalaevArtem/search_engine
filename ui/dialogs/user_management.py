from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QInputDialog, QLineEdit, QMessageBox
)
from models.database import SessionLocal, User, Role
from core.auth_manager import hash_password

class UserManagementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление пользователями")
        self.setMinimumSize(600, 400)
        self._apply_dark_theme()

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Логин", "Роли", "Активен"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        self.btn_create = QPushButton("Создать пользователя")
        self.btn_create_role = QPushButton("Создать роль")
        self.btn_toggle = QPushButton("Блок/Разблок")
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setObjectName("danger")
        btns.addWidget(self.btn_create)
        btns.addWidget(self.btn_create_role)
        btns.addWidget(self.btn_toggle)
        btns.addWidget(self.btn_delete)
        layout.addLayout(btns)

        self.btn_create.clicked.connect(self.create_user)
        self.btn_create_role.clicked.connect(self.create_role)
        self.btn_toggle.clicked.connect(self.toggle_active)
        self.btn_delete.clicked.connect(self.delete_user)
        self.load_users()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QLabel {
                color: #D4D4D4;
                font-size: 13px;
            }
            QTableWidget {
                background-color: #252526;
                color: #D4D4D4;
                gridline-color: #3E3E42;
                border: 1px solid #3E3E42;
                font-size: 13px;
                alternate-background-color: #2D2D30;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #3E3E42;
            }
            QHeaderView::section {
                background-color: #2D2D30;
                color: #D4D4D4;
                padding: 8px;
                border: 1px solid #3E3E42;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
            QPushButton#danger {
                background-color: #F85149;
            }
            QPushButton#danger:hover {
                background-color: #FF6B64;
            }
            QPushButton#danger:pressed {
                background-color: #C62E28;
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
            QComboBox {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
                min-height: 28px;
            }
            QComboBox:focus {
                border: 1px solid #0E639C;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #3E3E42;
                selection-background-color: #0E639C;
            }
            QMessageBox {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QMessageBox QPushButton {
                min-width: 80px;
            }
        """)

    def load_users(self):
        db = SessionLocal()
        try:
            users = db.query(User).all()
            self.table.setRowCount(len(users))
            for i, u in enumerate(users):
                self.table.setItem(i, 0, QTableWidgetItem(str(u.id)))
                self.table.setItem(i, 1, QTableWidgetItem(u.username))
                roles = ", ".join([r.name for r in u.roles])
                self.table.setItem(i, 2, QTableWidgetItem(roles))
                self.table.setItem(i, 3, QTableWidgetItem("Да" if u.is_active else "Нет"))
        finally:
            db.close()

    def create_role(self):
        name, ok = QInputDialog.getText(self, "Новая роль", "Имя роли:")
        if not ok or not name.strip():
            return
        db = SessionLocal()
        try:
            if db.query(Role).filter(Role.name == name.strip()).first():
                QMessageBox.warning(self, "Ошибка", "Роль уже существует")
                return
            db.add(Role(name=name.strip(), description=""))
            db.commit()
            QMessageBox.information(self, "Успех", f"Роль '{name}' создана")
        finally:
            db.close()

    def create_user(self):
        username, ok1 = QInputDialog.getText(self, "Новый пользователь", "Логин:")
        if not ok1 or not username.strip():
            return
        password, ok2 = QInputDialog.getText(self, "Новый пользователь", "Пароль:", QLineEdit.EchoMode.Password)
        if not ok2:
            return

        db = SessionLocal()
        try:
            roles = db.query(Role).all()
            if not roles:
                QMessageBox.warning(self, "Ошибка", "Сначала создайте роль")
                return

            role_names = [r.name for r in roles]
            role_name, ok3 = QInputDialog.getItem(self, "Выбор роли", "Роль:", role_names, 0, False)
            if not ok3:
                return

            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                return

            if db.query(User).filter(User.username == username).first():
                QMessageBox.warning(self, "Ошибка", "Пользователь уже существует")
                return

            new_user = User(username=username.strip(), password_hash=hash_password(password), is_active=True)
            new_user.roles.append(role)
            db.add(new_user)
            db.commit()
            self.load_users()
        finally:
            db.close()

    def toggle_active(self):
        row = self.table.currentRow()
        if row == -1:
            return
        uid = int(self.table.item(row, 0).text())
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == uid).first()
            if u:
                u.is_active = not u.is_active
                db.commit()
                self.load_users()
        finally:
            db.close()

    def delete_user(self):
        row = self.table.currentRow()
        if row == -1:
            return
        uid = int(self.table.item(row, 0).text())
        if QMessageBox.question(self, "Подтверждение", "Удалить пользователя?") != QMessageBox.StandardButton.Yes:
            return
        db = SessionLocal()
        try:
            db.query(User).filter(User.id == uid).delete()
            db.commit()
            self.load_users()
        finally:
            db.close()