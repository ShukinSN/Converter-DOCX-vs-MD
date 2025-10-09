# Импорты необходимых модулей из PyQt5 для создания UI-элементов
from PyQt5.QtWidgets import (
    QWidget,  # Базовый виджет для контейнера
    QVBoxLayout,  # Вертикальный layout для основного размещения
    QHBoxLayout,  # Горизонтальный layout для строк элементов
    QLabel,  # Метки для текста
    QLineEdit,  # Поля ввода
    QComboBox,  # Выпадающие списки
    QPushButton,  # Кнопки
    QGroupBox,  # Групповые боксы для разделения UI
    QListWidget,  # Список файлов
    QListWidgetItem,  # Элементы списка
    QMessageBox,  # Диалоги сообщений
    QCheckBox,  # Чекбоксы
    QFileDialog,  # Диалог для выбора файлов и папок
)
from PyQt5.QtCore import Qt, QSize  # Для флагов выравнивания, состояний и размера
from PyQt5.QtGui import QIcon  # Для работы с иконками
from pathlib import Path  # Для работы с путями к файлам

import resources_rc

# Импорты из модуля API для взаимодействия с BookStack
from converter.bookstack_api import (
    get_shelves,  # Получить список полок
    get_books_in_shelf,  # Получить книги в полке
    create_or_get_shelf,  # Создать или получить полку
    create_or_get_book_in_shelf,  # Создать или получить книгу
    create_page_from_md,  # Создать страницу из MD-файла
)

# Стандартные библиотеки для ОС и subprocess
import os
import sys
import subprocess


class BookStackWidget(QWidget):
    """
    Виджет для вкладки BookStack в главном окне.
    Отвечает за UI и логику загрузки файлов в BookStack.
    """

    def __init__(self, parent, converted_files, output_folder, project_root):
        """
        Инициализация виджета.
        :param parent: Родительское окно (DocxToMarkdownConverter)
        :param converted_files: Список путей к конвертированным MD-файлам
        :param output_folder: Папка вывода для файлов
        :param project_root: Корень проекта для путей
        """
        super().__init__(parent)
        self.parent_window = parent
        self.converted_files = converted_files
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.shelves = []  # Список полок из API
        self.books = []  # Список книг в текущей полке
        self.init_ui()  # Создание UI
        self.update_file_list()  # Обновление списка файлов

    def init_ui(self):
        """
        Создание и настройка UI-элементов виджета.
        """
        # Основной горизонтальный layout для разделения на левую и правую части
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(12)  # Отступы между частями

        # Левая часть: основное содержимое
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)

        # Группа для настроек подключения (URL и Token) - сверху
        connection_group = QGroupBox("Настройки подключения")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(8)

        # Строка для URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        self.bookstack_url_edit = QLineEdit()
        self.bookstack_url_edit.setPlaceholderText("URL BookStack")
        url_layout.addWidget(
            self.bookstack_url_edit, 1
        )  # Stretch = 1 для заполнения ширины
        url_layout.addStretch()  # Растяжение для выравнивания
        connection_layout.addLayout(url_layout)

        # Строка для токена
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Token:"))
        self.bookstack_token_edit = QLineEdit()
        self.bookstack_token_edit.setPlaceholderText("Token (Key ID:Secret)")
        self.bookstack_token_edit.setEchoMode(QLineEdit.Password)
        token_layout.addWidget(
            self.bookstack_token_edit, 1
        )  # Stretch = 1 для заполнения ширины
        token_layout.addStretch()  # Растяжение для выравнивания
        connection_layout.addLayout(token_layout)

        connection_group.setLayout(connection_layout)
        left_layout.addWidget(connection_group)

        # Группа для настроек загрузки (Полка и Книга)
        upload_group = QGroupBox("Настройки загрузки")
        shelf_layout = QHBoxLayout()
        shelf_layout.setSpacing(8)
        self.shelf_combo = QComboBox()
        self.shelf_combo.currentIndexChanged.connect(
            self.refresh_books
        )  # Сигнал для обновления книг
        self.refresh_shelves_btn = QPushButton()
        refresh_icon = QIcon(":/icons/refresh.png")
        self.refresh_shelves_btn.setIcon(refresh_icon)
        self.refresh_shelves_btn.setIconSize(QSize(24, 24))
        self.refresh_shelves_btn.clicked.connect(self.refresh_shelves)
        self.new_shelf_cb = QCheckBox("Создать новую полку")
        self.new_shelf_cb.stateChanged.connect(self.toggle_new_shelf)
        self.new_shelf_edit = QLineEdit("Новая полка")
        self.new_shelf_edit.setEnabled(False)
        self.create_shelf_btn = QPushButton("Создать полку")
        self.create_shelf_btn.clicked.connect(self.create_shelf)
        self.create_shelf_btn.setEnabled(False)
        shelf_layout.addWidget(QLabel("Полка:"))
        shelf_layout.addWidget(self.shelf_combo, 1)
        shelf_layout.addWidget(self.refresh_shelves_btn)
        shelf_layout.addWidget(self.new_shelf_cb)
        shelf_layout.addWidget(self.new_shelf_edit)
        shelf_layout.addWidget(self.create_shelf_btn)
        shelf_layout.addStretch()

        book_layout = QHBoxLayout()
        book_layout.setSpacing(8)
        self.book_combo = QComboBox()
        self.new_book_cb = QCheckBox("Создать новую книгу")
        self.new_book_cb.stateChanged.connect(self.toggle_new_book)
        self.new_book_edit = QLineEdit("Новая книга")
        self.new_book_edit.setEnabled(False)
        self.create_book_btn = QPushButton("Создать книгу")
        self.create_book_btn.clicked.connect(self.create_book)
        self.create_book_btn.setEnabled(False)
        book_layout.addWidget(QLabel("Книга:"))
        book_layout.addWidget(self.book_combo, 1)
        book_layout.addWidget(self.new_book_cb)
        book_layout.addWidget(self.new_book_edit)
        book_layout.addWidget(self.create_book_btn)
        book_layout.addStretch()

        upload_layout = QVBoxLayout()
        upload_layout.setSpacing(8)
        upload_layout.addLayout(shelf_layout)
        upload_layout.addLayout(book_layout)
        upload_group.setLayout(upload_layout)
        left_layout.addWidget(upload_group)

        # Группа для списка файлов с кнопками справа
        file_group = QGroupBox("Конвертированные файлы")
        file_layout = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(
            QListWidget.ExtendedSelection
        )  # Поддержка множественного выбора
        file_layout.addWidget(self.file_list)

        # Панель кнопок справа в столбик
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
        button_layout.addStretch()  # Растяжение для выравнивания

        file_layout.addLayout(button_layout)
        file_group.setLayout(file_layout)
        left_layout.addWidget(file_group)

        # Нижняя панель кнопок
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.upload_btn = QPushButton("Загрузить в BookStack")
        self.upload_btn.clicked.connect(self.upload_to_bookstack)
        btn_layout.addStretch()
        btn_layout.addWidget(self.upload_btn)
        left_layout.addLayout(btn_layout)

        # Правая часть: пустая, так как кнопки перемещены
        right_layout = QVBoxLayout()
        right_layout.addStretch()

        # Добавление левой и правой частей в основной layout
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 0)

    def toggle_new_shelf(self, state):
        """
        Переключение режима создания новой полки.
        :param state: Состояние чекбокса (Qt.Checked или Qt.Unchecked)
        """
        self.new_shelf_edit.setEnabled(state == Qt.Checked)
        self.create_shelf_btn.setEnabled(state == Qt.Checked)
        self.shelf_combo.setEnabled(not (state == Qt.Checked))

    def toggle_new_book(self, state):
        """
        Переключение режима создания новой книги.
        :param state: Состояние чекбокса (Qt.Checked или Qt.Unchecked)
        """
        self.new_book_edit.setEnabled(state == Qt.Checked)
        self.create_book_btn.setEnabled(state == Qt.Checked)
        self.book_combo.setEnabled(not (state == Qt.Checked))

    def create_shelf(self):
        """
        Создание новой полки по нажатию кнопки.
        """
        shelf_name = self.new_shelf_edit.text().strip()
        if not shelf_name:
            QMessageBox.warning(self, "Ошибка", "Укажите имя новой полки")
            return

        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен BookStack")
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }

        try:
            bs_url = url.rstrip("/")  # Удаление trailing slash
            shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
            if shelf_id is None:
                raise RuntimeError("Не удалось создать полку")
            QMessageBox.information(
                self, "Успех", f"Полка '{shelf_name}' создана (ID: {shelf_id})"
            )
            self.refresh_shelves()
            self.new_shelf_cb.setChecked(False)
            self.new_shelf_edit.clear()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка создания полки: {str(e)}")

    def create_book(self):
        """
        Создание новой книги по нажатию кнопки (требует выбранной полки).
        """
        book_name = self.new_book_edit.text().strip()
        if not book_name:
            QMessageBox.warning(self, "Ошибка", "Укажите имя новой книги")
            return

        if self.shelf_combo.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите или создайте полку")
            return

        shelf_index = self.shelf_combo.currentIndex()
        shelf_id = self.shelves[shelf_index]["id"]

        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен BookStack")
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }

        try:
            bs_url = url.rstrip("/")
            book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
            if book_id is None:
                raise RuntimeError("Не удалось создать книгу")
            QMessageBox.information(
                self, "Успех", f"Книга '{book_name}' создана (ID: {book_id})"
            )
            self.refresh_books(shelf_index)
            self.new_book_cb.setChecked(False)
            self.new_book_edit.clear()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка создания книги: {str(e)}")

    def update_file_list(self):
        """
        Обновление списка конвертированных файлов в QListWidget.
        """
        self.file_list.clear()
        for md_path in self.converted_files:
            item = QListWidgetItem(Path(md_path).name)
            self.file_list.addItem(item)

    def add_files(self):
        """
        Добавление файлов через диалог выбора.
        """
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите файлы",
            str(self.project_root),
            "Markdown files (*.md);;All files (*)",
        )
        if files:
            self.converted_files.extend(files)
            self.update_file_list()

    def add_folder(self):
        """
        Добавление всех файлов из выбранной папки.
        """
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку", str(self.project_root)
        )
        if folder:
            md_files = [
                os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".md")
            ]
            if md_files:
                self.converted_files.extend(md_files)
                self.update_file_list()
            else:
                QMessageBox.warning(self, "Предупреждение", "В папке нет файлов .md")

    def remove_selected(self):
        """
        Удаление выбранных элементов из списка.
        """
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Выберите файлы для удаления")
            return
        for item in selected_items:
            file_name = item.text()
            self.converted_files = [
                f for f in self.converted_files if Path(f).name != file_name
            ]
        self.update_file_list()

    def clear_list(self):
        """
        Очистка всего списка файлов.
        """
        if self.converted_files:
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Очистить список файлов?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.converted_files.clear()
                self.update_file_list()

    def go_back(self):
        """
        Переключение на вкладку конвертации.
        """
        self.parent_window.tab_widget.setCurrentIndex(0)

    def open_output_folder(self):
        """
        Открытие папки с выходными файлами в файловом менеджере.
        """
        try:
            if os.name == "nt":  # Windows
                os.startfile(self.output_folder)
            elif os.name == "posix":  # Linux/Mac
                if sys.platform == "darwin":  # Mac
                    subprocess.Popen(["open", self.output_folder])
                else:  # Linux
                    subprocess.Popen(["xdg-open", self.output_folder])
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку: {str(e)}")

    def refresh_shelves(self):
        """
        Обновление списка полок из API BookStack.
        """
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        if not all([url, token]):
            QMessageBox.warning(self, "Ошибка", "Укажите URL и токен BookStack")
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }

        try:
            bs_url = url.rstrip("/")  # Удаление trailing slash
            shelves_resp = get_shelves(bs_url, headers)  # Вызов API
            if shelves_resp is None:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить список полок")
                return

            self.shelves = shelves_resp  # Сохранение списка полок
            self.shelf_combo.clear()  # Очистка комбо-бокса
            for shelf in shelves_resp:
                self.shelf_combo.addItem(
                    f"{shelf['name']} (ID: {shelf['id']})"
                )  # Добавление элементов
            self.shelf_combo.setCurrentIndex(0)  # Выбор первой полки

            # Обновляем книги для первой полки
            if shelves_resp:
                self.refresh_books(0)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления полок: {str(e)}")

    def refresh_books(self, shelf_index):
        """
        Обновление списка книг для выбранной полки.
        :param shelf_index: Индекс выбранной полки
        """
        if not self.shelves or shelf_index < 0 or shelf_index >= len(self.shelves):
            self.book_combo.clear()
            return
        shelf_id = self.shelves[shelf_index]["id"]  # ID полки
        url = self.bookstack_url_edit.text().strip()
        token = self.bookstack_token_edit.text().strip()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {token}",
        }

        try:
            bs_url = url.rstrip("/")
            books_resp = get_books_in_shelf(bs_url, headers, shelf_id)  # Вызов API
            if books_resp is None:
                self.book_combo.clear()
                QMessageBox.warning(
                    self, "Предупреждение", "Не удалось получить список книг"
                )
                return

            self.books = books_resp  # Сохранение списка книг
            self.book_combo.clear()  # Очистка комбо-бокса
            for book in books_resp:
                self.book_combo.addItem(f"{book['name']} (ID: {book['id']})")
            if books_resp:  # Выбор первой книги, если список не пуст
                self.book_combo.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления книг: {str(e)}")
            self.book_combo.clear()

    def upload_to_bookstack(self):
        """
        Основная функция загрузки файлов в BookStack.
        Вызывает API для создания/получения полки, книги и страниц.
        """
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
