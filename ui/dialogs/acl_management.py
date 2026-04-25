from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QInputDialog, QMessageBox
)
from models.database import SessionLocal, DocumentACL
import core.access_control
from core.access_control import invalidate_acl_cache

class ACLManagementDialog(QDialog):
    """Диалог управления правилами доступа к файлам/папкам."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление доступом (ACL)")
        self.setMinimumSize(650, 400)
        self.setStyleSheet("""
            QDialog { background-color: #18191c; color: #e0e0e0; }
            QPushButton { background-color: #7289da; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #5f73bc; }
            QPushButton.danger { background-color: #f04747; }
            QTableWidget { background-color: #23272a; color: #e0e0e0; gridline-color: #333; }
        """)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Маска пути", "Доступно ролям", "Рекурсивно"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        btns = QHBoxLayout()
        self.btn_add = QPushButton("Добавить правило")
        self.btn_delete = QPushButton("Удалить выбранное")
        self.btn_delete.setObjectName("danger")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_delete)
        layout.addLayout(btns)
        self.btn_add.clicked.connect(self.add_rule)
        self.btn_delete.clicked.connect(self.delete_rule)
        self.load_rules()

    def load_rules(self):
        db = SessionLocal()
        try:
            rules = db.query(DocumentACL).all()
            self.table.setRowCount(len(rules))
            for i, r in enumerate(rules):
                self.table.setItem(i, 0, QTableWidgetItem(str(r.id)))
                self.table.setItem(i, 1, QTableWidgetItem(r.path_mask))
                self.table.setItem(i, 2, QTableWidgetItem(r.allowed_roles))
                self.table.setItem(i, 3, QTableWidgetItem("Да" if getattr(r, 'is_recursive', False) else "Нет"))
        finally:
            db.close()

    def add_rule(self):
        path, ok1 = QInputDialog.getText(self, "Новое правило", "Маска пути (напр. D:\\Docs\\* или *.pdf):")
        if not ok1 or not path.strip():
            return
        roles, ok2 = QInputDialog.getText(self, "Новое правило", "Роли через запятую (admin,user):")
        if not ok2 or not roles.strip():
            return
        recursive = QMessageBox.question(self, "Рекурсия?", "Применять к вложенным файлам и папкам?") == QMessageBox.StandardButton.Yes

        from models.database import SessionLocal, DocumentACL
        from sqlalchemy.exc import IntegrityError
        import core.access_control

        db = SessionLocal()
        try:
            db.add(DocumentACL(
                path_mask=path.strip().lower(),
                allowed_roles=roles.strip().replace(" ", ""),
                is_recursive=recursive
            ))
            db.commit()
            invalidate_acl_cache()
            self.load_rules()
            core.access_control._cached_acl = None
        except IntegrityError:
            db.rollback()
            QMessageBox.warning(self, "Ошибка", "Такое правило уже существует.")
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить правило: {e}")
        finally:
            db.close()

    def delete_rule(self):
        row = self.table.currentRow()
        if row == -1:
            return
        rule_id = int(self.table.item(row, 0).text())
        mask = self.table.item(row, 1).text()
        if QMessageBox.question(self, "Подтверждение", f"Удалить правило '{mask}'?") != QMessageBox.StandardButton.Yes:
            return
        db = SessionLocal()
        try:
            db.query(DocumentACL).filter(DocumentACL.id == rule_id).delete()
            db.commit()
            invalidate_acl_cache()
            self.load_rules()
            core.access_control._cached_acl = None
        finally:
            db.close()