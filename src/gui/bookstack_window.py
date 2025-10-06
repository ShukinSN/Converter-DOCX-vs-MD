from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QGroupBox,
    QListWidget,
    QMessageBox,
    QCheckBox,
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont
from pathlib import Path
import os
import subprocess
import sys
from converter.bookstack_api import (
    get_shelves,
    get_books_in_shelf,
    create_or_get_shelf,
    create_or_get_book_in_shelf,
    create_page_from_md,
)


class BookStackWindow(QMainWindow):
    def __init__(self, parent, converted_files, output_folder, project_root):
        super().__init__(parent)
        self.parent_window = parent
        self.converted_files = converted_files
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.settings = QSettings("DOCX2MD", "BookStackIntegration")
        self.shelves = []  # Список полок
        self.books = []  # Список книг в текущей полке
        self.init_ui()
        self.load_settings()
        self.update_file_list()

    def init_ui(self):
        self.setWindowTitle("Этап 2: Загрузка в BookStack")
        self.setGeometry(150, 150, 900, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Список конвертированных файлов
        file_group = QGroupBox("Конвертированные файлы")
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.NoSelection)
        file_group.setLayout(QVBoxLayout())
        file_group.layout().addWidget(self.file_list)
        layout.addWidget(file_group)

        # Настройки BookStack
        settings_group = QGroupBox("Настройки BookStack")
        self.bookstack_url_edit = QLineEdit("https://doc.tncpa.ru")
        self.bookstack_url_edit.setPlaceholderText("URL BookStack")
        self.bookstack_token_edit = QLineEdit()
        self.bookstack_token_edit.setPlaceholderText("Token (Key ID:Secret)")
        self.bookstack_token_edit.setEchoMode(QLineEdit.Password)

        # Выбор полки
        shelf_layout = QHBoxLayout()
        self.shelf_combo = QComboBox()
        self.refresh_shelves_btn = QPushButton("Обновить список полок")
        self.refresh_shelves_btn.clicked.connect(self.refresh_shelves)
        self.new_shelf_cb = QCheckBox("Создать новую полку")
        self.new_shelf_cb.stateChanged.connect(self.toggle_new_shelf)
        self.new_shelf_edit = QLineEdit("Новая полка")
        self.new_shelf_edit.setEnabled(False)
        shelf_layout.addWidget(QLabel("Полка:"))
        shelf_layout.addWidget(self.shelf_combo)
        shelf_layout.addWidget(self.refresh_shelves_btn)
        shelf_layout.addWidget(self.new_shelf_cb)
        shelf_layout.addWidget(self.new_shelf_edit)

        # Выбор книги
        book_layout = QHBoxLayout()
        self.book_combo = QComboBox()
        self.new_book_cb = QCheckBox("Создать новую книгу")
        self.new_book_cb.stateChanged.connect(self.toggle_new_book)
        self.new_book_edit = QLineEdit("Новая книга")
        self.new_book_edit.setEnabled(False)
        book_layout.addWidget(QLabel("Книга:"))
        book_layout.addWidget(self.book_combo)
        book_layout.addWidget(self.new_book_cb)
        book_layout.addWidget(self.new_book_edit)

        settings_layout = QVBoxLayout()
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.bookstack_url_edit)
        settings_layout.addLayout(url_layout)

        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Token:"))
        token_layout.addWidget(self.bookstack_token_edit)
        settings_layout.addLayout(token_layout)

        settings_layout.addLayout(shelf_layout)
        settings_layout.addLayout(book_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Кнопки навигации
        btn_layout = QHBoxLayout()
        self.back_btn = QPushButton("← Вернуться к конвертации")
        self.back_btn.clicked.connect(self.go_back)

        self.open_folder_btn = QPushButton("Открыть папку с файлами")
        self.open_folder_btn.clicked.connect(self.open_output_folder)

        self.upload_btn = QPushButton("Загрузить в BookStack")
        self.upload_btn.clicked.connect(self.upload_to_bookstack)

        self.finish_btn = QPushButton("Завершить")
        self.finish_btn.clicked.connect(self.close)

        btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addWidget(self.finish_btn)
        layout.addLayout(btn_layout)

    def update_file_list(self):
        self.file_list.clear()
        for file_path in self.converted_files:
            item = f"• {Path(file_path).name}"
            self.file_list.addItem(item)

    def refresh_shelves(self):
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(
                self, "Ошибка", "Укажите URL и токен для обновления списка"
            )
            return

        headers = {"Accept": "application/json", "Authorization": f"Token {token}"}

        bs_url = url.rstrip("/")
        self.shelves = get_shelves(bs_url, headers) or []
        self.shelf_combo.clear()
        for shelf in self.shelves:
            self.shelf_combo.addItem(
                f"{shelf['name']} (ID: {shelf['id']})", shelf["id"]
            )
        if self.shelves:
            self.shelf_combo.currentTextChanged.connect(self.on_shelf_changed)

    def on_shelf_changed(self, text):
        shelf_id = self.shelf_combo.currentData()
        if shelf_id:
            self.books = (
                get_books_in_shelf(
                    self.bookstack_url_edit.text().rstrip("/"),
                    {
                        "Accept": "application/json",
                        "Authorization": f"Token {self.bookstack_token_edit.text().strip()}",
                    },
                    shelf_id,
                )
                or []
            )
            self.book_combo.clear()
            for book in self.books:
                self.book_combo.addItem(
                    f"{book['name']} (ID: {book['id']})", book["id"]
                )

    def toggle_new_shelf(self, state):
        self.new_shelf_edit.setEnabled(state == Qt.Checked)
        if state == Qt.Checked:
            self.shelf_combo.setEnabled(False)
        else:
            self.shelf_combo.setEnabled(True)

    def toggle_new_book(self, state):
        self.new_book_edit.setEnabled(state == Qt.Checked)
        if state == Qt.Checked:
            self.book_combo.setEnabled(False)
        else:
            self.book_combo.setEnabled(True)

    def go_back(self):
        self.save_settings()
        self.close()

    def open_output_folder(self):
        try:
            if os.name == "nt":
                os.startfile(self.output_folder)
            elif os.name == "posix":
                if sys.platform == "darwin":
                    subprocess.Popen(["open", self.output_folder])
                else:
                    subprocess.Popen(["xdg-open", self.output_folder])
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку: {str(e)}")

    def upload_to_bookstack(self):
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен BookStack")
            return

        if not self.converted_files:
            QMessageBox.warning(self, "Ошибка", "Нет файлов для загрузки")
            return

        if self.new_shelf_cb.isChecked() and not self.new_shelf_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Укажите имя новой полки")
            return

        if self.new_book_cb.isChecked() and not self.new_book_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Укажите имя новой книги")
            return

        if not self.new_shelf_cb.isChecked() and self.shelf_combo.count() == 0:
            QMessageBox.warning(
                self, "Ошибка", "Обновите список полок или создайте новую"
            )
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }

        try:
            bs_url = url.rstrip("/")

            # Получить или создать полку
            shelf_name = (
                self.new_shelf_edit.text().strip()
                if self.new_shelf_cb.isChecked()
                else self.shelf_combo.currentText().split(" (")[0]
            )
            shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
            if shelf_id is None:
                raise RuntimeError("Не удалось создать или найти полку")
            QMessageBox.information(
                self, "Успех", f"Полка: {shelf_name} (ID: {shelf_id})"
            )

            # Получить или создать книгу
            book_name = (
                self.new_book_edit.text().strip()
                if self.new_book_cb.isChecked()
                else self.book_combo.currentText().split(" (")[0]
            )
            book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
            if book_id is None:
                raise RuntimeError("Не удалось создать или найти книгу")

            # Создать страницы для всех файлов в этой книге
            success_count = 0
            for md_path in self.converted_files:
                page_success = create_page_from_md(bs_url, headers, book_id, md_path)
                if page_success:
                    success_count += 1

            QMessageBox.information(
                self,
                "Завершено",
                f"Загружено {success_count}/{len(self.converted_files)} файлов в книгу '{book_name}'",
            )

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки: {str(e)}")

    def load_settings(self):
        self.bookstack_url_edit.setText(
            self.settings.value("url", "https://doc.tncpa.ru")
        )
        self.bookstack_token_edit.setText(self.settings.value("token", ""))
        self.new_shelf_edit.setText(
            self.settings.value("new_shelf_name", "Новая полка")
        )
        self.new_book_edit.setText(self.settings.value("new_book_name", "Новая книга"))

    def save_settings(self):
        self.settings.setValue("url", self.bookstack_url_edit.text())
        self.settings.setValue("token", self.bookstack_token_edit.text())
        self.settings.setValue("new_shelf_name", self.new_shelf_edit.text())
        self.settings.setValue("new_book_name", self.new_book_edit.text())

    def closeEvent(self, event):
        self.save_settings()
        if self.parent_window:
            self.parent_window.bookstack_window = None
        event.accept()
