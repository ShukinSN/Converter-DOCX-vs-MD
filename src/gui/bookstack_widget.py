# gui/bookstack_widget.py
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QCheckBox,
    QFileDialog,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon
from pathlib import Path
import os
import resources_rc

from converter.bookstack_api import (
    get_shelves,
    get_books_in_shelf,
    create_or_get_shelf,
    create_or_get_book_in_shelf,
    upload_md_with_images,
)


class BookStackWidget(QWidget):
    def __init__(self, parent, converted_files, output_folder, project_root):
        super().__init__(parent)
        self.parent_window = parent
        self.converted_files = converted_files
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.shelves = []
        self.books = []
        self.init_ui()
        self.update_file_list()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(12)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)

        # === Настройки подключения ===
        connection_group = QGroupBox("Настройки подключения")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(8)

        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        self.bookstack_url_edit = QLineEdit()
        self.bookstack_url_edit.setPlaceholderText("https://doc.tncpa.ru")
        url_layout.addWidget(self.bookstack_url_edit, 1)
        connection_layout.addLayout(url_layout)

        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Token:"))
        self.bookstack_token_edit = QLineEdit()
        self.bookstack_token_edit.setPlaceholderText("Key ID:Secret")
        self.bookstack_token_edit.setEchoMode(QLineEdit.Password)
        token_layout.addWidget(self.bookstack_token_edit, 1)
        connection_layout.addLayout(token_layout)

        connection_group.setLayout(connection_layout)
        left_layout.addWidget(connection_group)

        # === Настройки загрузки ===
        upload_group = QGroupBox("Настройки загрузки")
        shelf_layout = QHBoxLayout()
        self.shelf_combo = QComboBox()
        self.shelf_combo.currentIndexChanged.connect(self.refresh_books)
        self.refresh_shelves_btn = QPushButton()
        self.refresh_shelves_btn.setIcon(QIcon(":/icons/refresh.png"))
        self.refresh_shelves_btn.setIconSize(QSize(24, 24))
        self.refresh_shelves_btn.clicked.connect(self.refresh_shelves)
        self.new_shelf_cb = QCheckBox("Создать новую полку")
        self.new_shelf_cb.stateChanged.connect(self.toggle_new_shelf)
        self.new_shelf_edit = QLineEdit("Новая полка")
        self.new_shelf_edit.setEnabled(False)
        self.create_shelf_btn = QPushButton("Создать")
        self.create_shelf_btn.clicked.connect(self.create_shelf)
        self.create_shelf_btn.setEnabled(False)
        shelf_layout.addWidget(QLabel("Полка:"))
        shelf_layout.addWidget(self.shelf_combo, 1)
        shelf_layout.addWidget(self.refresh_shelves_btn)
        shelf_layout.addWidget(self.new_shelf_cb)
        shelf_layout.addWidget(self.new_shelf_edit)
        shelf_layout.addWidget(self.create_shelf_btn)

        book_layout = QHBoxLayout()
        self.book_combo = QComboBox()
        self.new_book_cb = QCheckBox("Создать новую книгу")
        self.new_book_cb.stateChanged.connect(self.toggle_new_book)
        self.new_book_edit = QLineEdit("Новая книга")
        self.new_book_edit.setEnabled(False)
        self.create_book_btn = QPushButton("Создать")
        self.create_book_btn.clicked.connect(self.create_book)
        self.create_book_btn.setEnabled(False)
        book_layout.addWidget(QLabel("Книга:"))
        book_layout.addWidget(self.book_combo, 1)
        book_layout.addWidget(self.new_book_cb)
        book_layout.addWidget(self.new_book_edit)
        book_layout.addWidget(self.create_book_btn)

        upload_layout = QVBoxLayout()
        upload_layout.addLayout(shelf_layout)
        upload_layout.addLayout(book_layout)
        upload_group.setLayout(upload_layout)
        left_layout.addWidget(upload_group)

        # === Список файлов ===
        file_group = QGroupBox("Конвертированные файлы")
        file_layout = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        file_layout.addWidget(self.file_list)

        button_layout = QVBoxLayout()
        self.add_files_btn = QPushButton("Добавить файлы")
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn = QPushButton("Добавить папку")
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_selected_btn = QPushButton("Удалить выбранное")
        self.remove_selected_btn.clicked.connect(self.remove_selected)
        self.clear_list_btn = QPushButton("Очистить список")
        self.clear_list_btn.clicked.connect(self.clear_list)
        button_layout.addWidget(self.add_files_btn)
        button_layout.addWidget(self.add_folder_btn)
        button_layout.addWidget(self.remove_selected_btn)
        button_layout.addWidget(self.clear_list_btn)
        button_layout.addStretch()
        file_layout.addLayout(button_layout)
        file_group.setLayout(file_layout)
        left_layout.addWidget(file_group)

        # === Кнопка загрузки ===
        btn_layout = QHBoxLayout()
        self.upload_btn = QPushButton("Загрузить в BookStack")
        self.upload_btn.clicked.connect(self.upload_to_bookstack)
        btn_layout.addStretch()
        btn_layout.addWidget(self.upload_btn)
        left_layout.addLayout(btn_layout)

        main_layout.addLayout(left_layout, 1)
        main_layout.addStretch()

    def toggle_new_shelf(self, state):
        self.new_shelf_edit.setEnabled(state == Qt.Checked)
        self.create_shelf_btn.setEnabled(state == Qt.Checked)
        self.shelf_combo.setEnabled(not (state == Qt.Checked))

    def toggle_new_book(self, state):
        self.new_book_edit.setEnabled(state == Qt.Checked)
        self.create_book_btn.setEnabled(state == Qt.Checked)
        self.book_combo.setEnabled(not (state == Qt.Checked))

    def create_shelf(self):
        shelf_name = self.new_shelf_edit.text().strip()
        if not shelf_name:
            QMessageBox.warning(self, "Ошибка", "Укажите имя полки")
            return
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
            return
        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")
        shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
        if shelf_id:
            QMessageBox.information(self, "Успех", f"Полка создана (ID: {shelf_id})")
            self.refresh_shelves()
            self.new_shelf_cb.setChecked(False)

    def create_book(self):
        book_name = self.new_book_edit.text().strip()
        if not book_name or self.shelf_combo.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Выберите полку")
            return
        shelf_id = self.shelves[self.shelf_combo.currentIndex()]["id"]
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")
        book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
        if book_id:
            QMessageBox.information(self, "Успех", f"Книга создана (ID: {book_id})")
            self.refresh_books(self.shelf_combo.currentIndex())
            self.new_book_cb.setChecked(False)

    def update_file_list(self):
        self.file_list.clear()
        for md_path in self.converted_files:
            self.file_list.addItem(QListWidgetItem(Path(md_path).name))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать файлы", str(self.project_root), "Markdown (*.md)"
        )
        if files:
            self.converted_files.extend(files)
            self.update_file_list()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выбрать папку", str(self.project_root)
        )
        if folder:
            md_files = [
                os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".md")
            ]
            if md_files:
                self.converted_files.extend(md_files)
                self.update_file_list()

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            name = item.text()
            self.converted_files = [
                f for f in self.converted_files if Path(f).name != name
            ]
        self.update_file_list()

    def clear_list(self):
        if (
            self.converted_files
            and QMessageBox.question(
                self,
                "Подтверждение",
                "Очистить список?",
                QMessageBox.Yes | QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.converted_files.clear()
            self.update_file_list()

    def refresh_shelves(self):
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
            return
        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")
        shelves = get_shelves(bs_url, headers)
        if not shelves:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить полки")
            return
        self.shelves = shelves
        self.shelf_combo.clear()
        for s in shelves:
            self.shelf_combo.addItem(f"{s['name']} (ID: {s['id']})")
        self.shelf_combo.setCurrentIndex(0)
        self.refresh_books(0)

    def refresh_books(self, index):
        if index < 0 or not self.shelves:
            return
        shelf_id = self.shelves[index]["id"]
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")
        books = get_books_in_shelf(bs_url, headers, shelf_id)
        if books is None:
            return
        self.books = books
        self.book_combo.clear()
        for b in books:
            self.book_combo.addItem(f"{b['name']} (ID: {b['id']})")

    def upload_to_bookstack(self):
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
            return
        if not self.converted_files:
            QMessageBox.warning(self, "Ошибка", "Нет файлов")
            return

        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")

        shelf_name = (
            self.new_shelf_edit.text().strip()
            if self.new_shelf_cb.isChecked()
            else self.shelf_combo.currentText().split(" (")[0]
        )
        shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
        if not shelf_id:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать/найти полку")
            return

        book_name = (
            self.new_book_edit.text().strip()
            if self.new_book_cb.isChecked()
            else self.book_combo.currentText().split(" (")[0]
        )
        book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
        if not book_id:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать/найти книгу")
            return

        success_count = 0
        for md_path in self.converted_files:
            if upload_md_with_images(bs_url, headers, book_id, md_path):
                success_count += 1

        QMessageBox.information(
            self,
            "Готово!",
            f"Загружено {success_count}/{len(self.converted_files)} файлов\n"
            f"Изображения встроены в текст через Markdown",
        )
