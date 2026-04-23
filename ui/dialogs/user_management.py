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
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            QDialog { background-color: #18191c; color: #e0e0e0; }
            QPushButton { background-color: #43b581; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #3ca374; }
            QPushButton.danger { background-color: #f04747; }
            QPushButton.danger:hover { background-color: #d63c3c; }
            QTableWidget { background-color: #23272a; color: #e0e0e0; gridline-color: #333; }
        """)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Логин", "Роль", "Активен"])
        layout.addWidget(self.table)
        btns = QHBoxLayout()
        self.btn_create = QPushButton("Создать")
        self.btn_toggle = QPushButton("Блок/Разблок")
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setObjectName("danger")
        btns.addWidget(self.btn_create)
        btns.addWidget(self.btn_toggle)
        btns.addWidget(self.btn_delete)
        layout.addLayout(btns)
        self.btn_create.clicked.connect(self.create_user)
        self.btn_toggle.clicked.connect(self.toggle_active)
        self.btn_delete.clicked.connect(self.delete_user)
        self.load_users()

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

    def create_user(self):
        username, ok1 = QInputDialog.getText(self, "Новый пользователь", "Логин:")
        if not ok1 or not username.strip():
            return
        password, ok2 = QInputDialog.getText(self, "Новый пользователь", "Пароль:", QLineEdit.EchoMode.Password)
        if not ok2:
            return
        db = SessionLocal()
        try:
            if db.query(User).filter(User.username == username).first():
                QMessageBox.warning(self, "Ошибка", "Пользователь уже существует")
                return
            role = db.query(Role).filter(Role.name == "user").first()
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