# src/gui/bookstack_widget.py
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
    QTextEdit,
    QProgressBar,
    QDialog,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QIcon, QFont
from pathlib import Path
from tagger.smart_tagger import SmartTagger
from tagger.book_tagger import BookStackBookTagger
import os
import resources_rc
from converter.bookstack_api import (
    get_shelves,
    get_books_in_shelf,
    create_or_get_shelf,
    create_or_get_book_in_shelf,
    upload_md_with_images,
    create_or_get_chapter,
)


# === ПОТОК ЗАГРУЗКИ ===
class UploadWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(int)

    def __init__(self, base_url, headers, book_id, file_groups, auto_tags=True):
        super().__init__()
        self.base_url = base_url
        self.headers = headers
        self.book_id = book_id
        self.file_groups = file_groups  # list или dict
        self.auto_tags = auto_tags
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        # === СПИСОК → без глав ===
        if isinstance(self.file_groups, list):
            total = len(self.file_groups)
            if total == 0:
                self.finished.emit(0)
                return

            success = processed = 0
            for md_path in self.file_groups:
                if self._canceled:
                    break
                processed += 1
                filename = Path(md_path).name
                self.progress.emit(
                    int((processed / total) * 100), f"Загрузка: {filename}"
                )

                ok = upload_md_with_images(
                    self.base_url,
                    self.headers,
                    self.book_id,
                    md_path,
                    log_callback=lambda m, c: self.log.emit(m, c),
                    chapter_id=None,
                    auto_tags=self.auto_tags,
                )
                if ok:
                    success += 1
                    self.log.emit(f"Успешно: {filename}", "green")
                else:
                    self.log.emit(f"Ошибка: {filename}", "red")

            if not self._canceled:
                self.progress.emit(100, f"Готово: {success}/{total}")
                self.finished.emit(success)
            return

        # === DICT → с главами ===
        total = sum(len(files) for files in self.file_groups.values())
        if total == 0:
            self.finished.emit(0)
            return

        success = processed = 0
        for chapter_name, md_files in self.file_groups.items():
            if self._canceled:
                break

            chapter_id = create_or_get_chapter(
                self.base_url, self.headers, self.book_id, chapter_name
            )
            if not chapter_id:
                self.log.emit(f"Ошибка создания главы '{chapter_name}'", "red")
                continue
            self.log.emit(f"Глава: {chapter_name}", "orange")

            for md_path in md_files:
                if self._canceled:
                    break
                processed += 1
                filename = Path(md_path).name
                self.progress.emit(
                    int((processed / total) * 100), f"{filename} → {chapter_name}"
                )

                ok = upload_md_with_images(
                    self.base_url,
                    self.headers,
                    self.book_id,
                    md_path,
                    log_callback=lambda m, c: self.log.emit(m, c),
                    chapter_id=chapter_id,
                    auto_tags=self.auto_tags,
                )
                if ok:
                    success += 1
                    self.log.emit(f"Успешно: {filename}", "green")
                else:
                    self.log.emit(f"Ошибка: {filename}", "red")

        if not self._canceled:
            self.progress.emit(100, f"Готово: {success}/{total}")
            self.finished.emit(success)


class BookStackWidget(QWidget):
    def __init__(self, parent, converted_files, output_folder, project_root):
        super().__init__(parent)
        self.parent_window = parent
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.shelves = []
        self.books = []
        self.worker = None
        self.tagger = SmartTagger()

        # Используем настройки приложения для сохранения последнего пути
        self.settings = QSettings("DOCX2MD", "EnhancedConverter")
        self.last_path = self.settings.value(
            "bookstack_last_path", str(self.project_root)
        )

        self.converted_files = converted_files or []

        self.init_ui()
        self.update_file_list()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        top_layout = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(12)

        # === ПОДКЛЮЧЕНИЕ ===
        conn = QGroupBox("Подключение")
        cl = QVBoxLayout()
        url_l = QHBoxLayout()
        url_l.addWidget(QLabel("URL:"))
        self.url_edit = QLineEdit("https://doc.tncpa.ru")
        url_l.addWidget(self.url_edit, 1)
        cl.addLayout(url_l)
        token_l = QHBoxLayout()
        token_l.addWidget(QLabel("Token:"))
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("ID:Secret")
        token_l.addWidget(self.token_edit, 1)
        cl.addLayout(token_l)
        conn.setLayout(cl)
        left.addWidget(conn)

        # === ЗАГРУЗКА ===
        upload_g = QGroupBox("Загрузка")
        ul = QVBoxLayout()

        shelf_l = QHBoxLayout()
        self.shelf_combo = QComboBox()
        self.shelf_combo.currentIndexChanged.connect(self.refresh_books)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        self.refresh_btn.setIconSize(QSize(24, 24))
        self.refresh_btn.clicked.connect(self.refresh_shelves)
        self.new_shelf_cb = QCheckBox("Новая полка")
        self.new_shelf_cb.stateChanged.connect(self.toggle_new_shelf)
        self.new_shelf_edit = QLineEdit("Новая полка")
        self.new_shelf_edit.setEnabled(False)
        self.create_shelf_btn = QPushButton("Создать")
        self.create_shelf_btn.clicked.connect(self.create_shelf)
        self.create_shelf_btn.setEnabled(False)
        shelf_l.addWidget(QLabel("Полка:"))
        shelf_l.addWidget(self.shelf_combo, 1)
        shelf_l.addWidget(self.refresh_btn)
        shelf_l.addWidget(self.new_shelf_cb)
        shelf_l.addWidget(self.new_shelf_edit)
        shelf_l.addWidget(self.create_shelf_btn)
        ul.addLayout(shelf_l)

        book_l = QHBoxLayout()
        self.book_combo = QComboBox()
        self.new_book_cb = QCheckBox("Новая книга")
        self.new_book_cb.stateChanged.connect(self.toggle_new_book)
        self.new_book_edit = QLineEdit("Новая книга")
        self.new_book_edit.setEnabled(False)
        self.create_book_btn = QPushButton("Создать")
        self.create_book_btn.clicked.connect(self.create_book)
        self.create_book_btn.setEnabled(False)
        book_l.addWidget(QLabel("Книга:"))
        book_l.addWidget(self.book_combo, 1)
        book_l.addWidget(self.new_book_cb)
        book_l.addWidget(self.new_book_edit)
        book_l.addWidget(self.create_book_btn)
        ul.addLayout(book_l)

        tag_l = QHBoxLayout()
        self.auto_tags_cb = QCheckBox("Автотегирование")
        self.auto_tags_cb.setChecked(True)
        tag_l.addWidget(self.auto_tags_cb)
        self.preview_btn = QPushButton("Предпросмотр тегов")
        self.preview_btn.clicked.connect(self.show_tag_preview)
        tag_l.addWidget(self.preview_btn)
        self.tag_book_btn = QPushButton("Тегировать книгу")
        self.tag_book_btn.clicked.connect(self.tag_current_book)
        self.tag_book_btn.setEnabled(False)
        tag_l.addWidget(self.tag_book_btn)
        tag_l.addStretch()
        ul.addLayout(tag_l)

        upload_g.setLayout(ul)
        left.addWidget(upload_g)

        # === ФАЙЛЫ ===
        file_g = QGroupBox("Файлы")
        fl = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        fl.addWidget(self.file_list)
        btns = QVBoxLayout()
        self.add_files_btn = QPushButton("Добавить файлы")
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn = QPushButton("Добавить папку")
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_btn = QPushButton("Удалить выбранные")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Очистить список")
        self.clear_btn.clicked.connect(self.clear_list)
        btns.addWidget(self.add_files_btn)
        btns.addWidget(self.add_folder_btn)
        btns.addWidget(self.remove_btn)
        btns.addWidget(self.clear_btn)
        btns.addStretch()
        fl.addLayout(btns)
        file_g.setLayout(fl)
        left.addWidget(file_g)

        top_layout.addLayout(left, 1)
        main_layout.addLayout(top_layout)

        # === КНОПКИ ===
        bl = QHBoxLayout()
        bl.addStretch()
        self.upload_btn = QPushButton("Загрузить")
        self.upload_btn.clicked.connect(self.upload_to_bookstack)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_upload)
        self.cancel_btn.setEnabled(False)
        bl.addWidget(self.upload_btn)
        bl.addWidget(self.cancel_btn)
        main_layout.addLayout(bl)

        # === ПРОГРЕСС ===
        self.progress = QProgressBar()
        self.progress.setFormat("Готово")
        main_layout.addWidget(self.progress)

        # === ЛОГ ===
        log_g = QGroupBox("Лог")
        ll = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)
        self.log_text.setFont(QFont("Consolas", 9))
        ll.addWidget(self.log_text)
        log_g.setLayout(ll)
        main_layout.addWidget(log_g)

    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===
    def toggle_new_shelf(self, state):
        self.new_shelf_edit.setEnabled(state == Qt.Checked)
        self.create_shelf_btn.setEnabled(state == Qt.Checked)
        self.shelf_combo.setEnabled(not (state == Qt.Checked))

    def toggle_new_book(self, state):
        self.new_book_edit.setEnabled(state == Qt.Checked)
        self.create_book_btn.setEnabled(state == Qt.Checked)
        self.book_combo.setEnabled(not (state == Qt.Checked))

    def create_shelf(self):
        name = self.new_shelf_edit.text().strip()
        if not name:
            return QMessageBox.warning(self, "Ошибка", "Введите имя полки")
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
        headers = {"Authorization": f"Token {token}"}
        shelf_id = create_or_get_shelf(url.rstrip("/"), headers, name)
        if shelf_id:
            QMessageBox.information(self, "Успех", f"Полка создана (ID: {shelf_id})")
            self.refresh_shelves()
            self.new_shelf_cb.setChecked(False)

    def create_book(self):
        name = self.new_book_edit.text().strip()
        if not name or self.shelf_combo.count() == 0:
            return QMessageBox.warning(self, "Ошибка", "Выберите полку")
        shelf_id = self.shelves[self.shelf_combo.currentIndex()]["id"]
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        headers = {"Authorization": f"Token {token}"}
        book_id = create_or_get_book_in_shelf(url.rstrip("/"), headers, shelf_id, name)
        if book_id:
            QMessageBox.information(self, "Успех", f"Книга создана (ID: {book_id})")
            self.refresh_books(self.shelf_combo.currentIndex())
            self.new_book_cb.setChecked(False)

    def refresh_shelves(self):
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
        headers = {"Authorization": f"Token {token}"}
        shelves = get_shelves(url.rstrip("/"), headers)
        if not shelves:
            return QMessageBox.warning(self, "Ошибка", "Не удалось получить полки")
        self.shelves = shelves
        self.shelf_combo.clear()
        for s in shelves:
            self.shelf_combo.addItem(f"{s['name']} (ID: {s['id']})")
        self.shelf_combo.setCurrentIndex(0)
        self.refresh_books(0)

    def refresh_books(self, idx):
        if idx < 0 or not self.shelves:
            return
        shelf_id = self.shelves[idx]["id"]
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        headers = {"Authorization": f"Token {token}"}
        books = get_books_in_shelf(url.rstrip("/"), headers, shelf_id)
        if books is None:
            return
        self.books = books
        self.book_combo.clear()
        for b in books:
            self.book_combo.addItem(f"{b['name']} (ID: {b['id']})")
        self.tag_book_btn.setEnabled(bool(books))

    # === РАБОТА С ФАЙЛАМИ ===
    def update_file_list(self):
        self.file_list.clear()

        if isinstance(self.converted_files, list):
            for p in self.converted_files:
                item = QListWidgetItem(Path(p).name)
                item.setData(Qt.UserRole, p)  # Сохраняем полный путь
                try:
                    tags = self.tagger.get_document_tags(Path(p))
                    if tags:
                        item.setToolTip("Теги: " + ", ".join(tags) + f"\nПуть: {p}")
                    else:
                        item.setToolTip(f"Путь: {p}")
                except:
                    item.setToolTip(f"Путь: {p}")
                self.file_list.addItem(item)
            return

        if isinstance(self.converted_files, dict):
            for chapter_name, files in self.converted_files.items():
                if not files:  # ← НЕ показываем пустые главы
                    continue
                chapter_item = QListWidgetItem(
                    f"Глава: {chapter_name} ({len(files)} файлов)"
                )
                chapter_item.setBackground(Qt.lightGray)
                chapter_item.setData(Qt.UserRole, chapter_name)  # Сохраняем имя главы
                self.file_list.addItem(chapter_item)
                for p in files:
                    item = QListWidgetItem(f"   └ {Path(p).name}")
                    item.setData(Qt.UserRole, p)  # Сохраняем полный путь
                    try:
                        tags = self.tagger.get_document_tags(Path(p))
                        if tags:
                            item.setToolTip("Теги: " + ", ".join(tags) + f"\nПуть: {p}")
                        else:
                            item.setToolTip(f"Путь: {p}")
                    except:
                        item.setToolTip(f"Путь: {p}")
                    self.file_list.addItem(item)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать MD",
            self.last_path,
            "Markdown (*.md)",  # Используем last_path
        )
        if not files:
            return

        # Обновляем last_path на папку первого выбранного файла
        if files:
            self.last_path = str(Path(files[0]).parent)
            self.save_settings()  # Сохраняем настройки

        if isinstance(self.converted_files, list):
            # Добавляем полные пути к файлам
            self.converted_files.extend(files)
        elif isinstance(self.converted_files, dict):
            # Добавляем в главу "Без главы" с полными путями
            if "Без главы" not in self.converted_files:
                self.converted_files["Без главы"] = []
            self.converted_files["Без главы"].extend(files)
        else:
            # Если converted_files пустой или другого типа, создаем список с полными путями
            self.converted_files = files[:]

        self.update_file_list()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выбрать папку", self.last_path  # Используем last_path
        )
        if not folder:
            return

        # Обновляем last_path на выбранную папку
        self.last_path = folder
        self.save_settings()  # Сохраняем настройки

        folder_path = Path(folder)
        md_files = [
            str(folder_path / f) for f in os.listdir(folder) if f.endswith(".md")
        ]
        if not md_files:
            QMessageBox.information(self, "Пусто", "В выбранной папке нет .md файлов")
            return

        folder_name = folder_path.name

        if isinstance(self.converted_files, list):
            # Если был список, преобразуем в словарь
            if self.converted_files:
                self.converted_files = {"Без главы": self.converted_files[:]}
            else:
                self.converted_files = {}

        elif not isinstance(self.converted_files, dict):
            # Если был другой тип, создаем словарь
            self.converted_files = {}

        # Добавляем файлы с полными путями
        self.converted_files[folder_name] = md_files
        self.update_file_list()

    def remove_selected(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return

        # Собираем пути для удаления
        paths_to_remove = []
        for item in selected_items:
            path = item.data(Qt.UserRole)
            if path:  # Если это файл (а не заголовок главы)
                paths_to_remove.append(path)

        # Удаляем из converted_files
        if isinstance(self.converted_files, list):
            self.converted_files = [
                p for p in self.converted_files if p not in paths_to_remove
            ]
        elif isinstance(self.converted_files, dict):
            for chapter_name in list(self.converted_files.keys()):
                self.converted_files[chapter_name] = [
                    p
                    for p in self.converted_files[chapter_name]
                    if p not in paths_to_remove
                ]
                # Удаляем пустые главы
                if not self.converted_files[chapter_name]:
                    del self.converted_files[chapter_name]

        self.update_file_list()

    def clear_list(self):
        if (
            self.converted_files
            and QMessageBox.question(
                self,
                "Очистить?",
                "Очистить список файлов?",
                QMessageBox.Yes | QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.converted_files = []
            self.update_file_list()

    def save_settings(self):
        """Сохраняем последний путь в настройках"""
        self.settings.setValue("bookstack_last_path", self.last_path)

    def closeEvent(self, event):
        """При закрытии виджета сохраняем настройки"""
        self.save_settings()
        super().closeEvent(event)

    # === ТЕГИРОВАНИЕ ===
    def show_tag_preview(self):
        if not self.converted_files:
            return QMessageBox.information(self, "Инфо", "Нет файлов")

        files_to_check = (
            self.converted_files
            if isinstance(self.converted_files, list)
            else [f for fl in self.converted_files.values() for f in fl]
        )

        preview = "<b>Предпросмотр тегов:</b><br><br>"
        for p in files_to_check:
            tags = self.tagger.get_document_tags(Path(p))
            preview += f"<b>{Path(p).name}</b><br> → {', '.join(tags) if tags else '—'}<br><br>"

        dlg = QDialog(self)
        dlg.setWindowTitle("Предпросмотр тегов")
        dlg.resize(800, 600)
        l = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setHtml(preview)
        te.setReadOnly(True)
        l.addWidget(te)
        btn = QDialogButtonBox(QDialogButtonBox.Ok)
        btn.accepted.connect(dlg.accept)
        l.addWidget(btn)
        dlg.exec_()

    def tag_current_book(self):
        try:
            if self.book_combo.count() == 0:
                return QMessageBox.warning(
                    self, "Ошибка", "Нет доступных книг для тегирования"
                )

            # Получаем информацию о выбранной книге
            text = self.book_combo.currentText()
            name = text.split(" (ID: ")[0]
            book_id = int(text.split("ID: ")[1][:-1])

            # Проверяем авторизационные данные
            url = self.url_edit.text().strip()
            token = self.token_edit.text().strip()
            if not all([url, token]):
                return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен API")

            # Создаем экземпляр теггера (без log_callback)
            tagger = BookStackBookTagger(url.rstrip("/"), *token.split(":"))

            # Выполняем тегирование
            self.log_text.append(
                f'<font color="orange">Начато тегирование книги: «{name}»</font>'
            )

            if tagger.tag_book(book_id, name):
                QMessageBox.information(
                    self, "Успех", f"Книга «{name}» успешно тегирована"
                )
                self.log_text.append(
                    f'<font color="green">Тегирование книги «{name}» завершено успешно</font>'
                )
            else:
                QMessageBox.warning(
                    self, "Ошибка", f"Не удалось выполнить тегирование книги «{name}»"
                )
                self.log_text.append(
                    f'<font color="red">Ошибка тегирования книги «{name}»</font>'
                )

        except ValueError as e:
            error_msg = f"Ошибка формата данных: {str(e)}"
            QMessageBox.critical(self, "Ошибка", error_msg)
            self.log_text.append(f'<font color="red">{error_msg}</font>')
        except Exception as e:
            error_msg = f"Произошла непредвиденная ошибка: {str(e)}"
            QMessageBox.critical(self, "Ошибка", error_msg)
            self.log_text.append(f'<font color="red">{error_msg}</font>')

    # === ЗАГРУЗКА ===
    def upload_to_bookstack(self):
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")

        if not self.converted_files:
            return QMessageBox.warning(self, "Ошибка", "Нет файлов для загрузки")

        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")

        # === ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ДЛЯ ДИАГНОСТИКИ ===
        self.log_text.clear()
        self.log_text.append(f'<font color="#00ffff">=== НАЧАЛО ЗАГРУЗКИ ===</font>')
        self.log_text.append(f'<font color="gray">URL: {bs_url}</font>')

        # Получаем имя полки
        if self.new_shelf_cb.isChecked():
            shelf_name = self.new_shelf_edit.text().strip()
            self.log_text.append(
                f'<font color="orange">НОВАЯ ПОЛКА: {shelf_name}</font>'
            )
        else:
            if self.shelf_combo.count() == 0:
                return QMessageBox.warning(self, "Ошибка", "Выберите полку")
            shelf_text = self.shelf_combo.currentText()
            shelf_name = (
                shelf_text.split(" (ID: ")[0] if " (ID: " in shelf_text else shelf_text
            )
            self.log_text.append(
                f'<font color="green">ВЫБРАНА ПОЛКА: {shelf_name}</font>'
            )

        # Создаем/получаем полку
        self.log_text.append(
            f'<font color="gray">Создание/поиск полки: {shelf_name}</font>'
        )
        shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
        if not shelf_id:
            error_msg = f"Не удалось создать/найти полку '{shelf_name}'"
            self.log_text.append(f'<font color="red">{error_msg}</font>')
            return QMessageBox.critical(self, "Ошибка", error_msg)

        self.log_text.append(
            f'<font color="green">Полка найдена/создана: ID {shelf_id}</font>'
        )

        # Получаем имя книги
        if self.new_book_cb.isChecked():
            book_name = self.new_book_edit.text().strip()
            if not book_name:
                return QMessageBox.warning(self, "Ошибка", "Введите имя новой книги")
            self.log_text.append(
                f'<font color="orange">НОВАЯ КНИГА: {book_name}</font>'
            )
        else:
            if self.book_combo.count() == 0:
                return QMessageBox.warning(self, "Ошибка", "Выберите книгу")
            book_text = self.book_combo.currentText()
            # Более надежное извлечение имени книги и ID
            if " (ID: " in book_text:
                book_name = book_text.split(" (ID: ")[0]
                try:
                    selected_book_id = int(book_text.split(" (ID: ")[1].rstrip(")"))
                    self.log_text.append(
                        f'<font color="green">ВЫБРАНА КНИГА: {book_name} (ID: {selected_book_id})</font>'
                    )
                except:
                    selected_book_id = None
                    self.log_text.append(
                        f'<font color="green">ВЫБРАНА КНИГА: {book_name}</font>'
                    )
            else:
                book_name = book_text
                selected_book_id = None
                self.log_text.append(
                    f'<font color="green">ВЫБРАНА КНИГА: {book_name}</font>'
                )

        # Если выбрана существующая книга, используем её ID напрямую
        if not self.new_book_cb.isChecked() and selected_book_id:
            self.log_text.append(
                f'<font color="#00ffff">Используем существующую книгу с ID: {selected_book_id}</font>'
            )
            book_id = selected_book_id

            # Проверяем, что книга действительно в выбранной полке
            try:
                shelf_books = get_books_in_shelf(bs_url, headers, shelf_id)
                if shelf_books:
                    book_in_shelf = any(
                        b["id"] == selected_book_id for b in shelf_books
                    )
                    if not book_in_shelf:
                        self.log_text.append(
                            f'<font color="red">ОШИБКА: Книга "{book_name}" не найдена в полке "{shelf_name}"!</font>'
                        )
                        return QMessageBox.critical(
                            self,
                            "Ошибка",
                            f'Книга "{book_name}" не найдена в полке "{shelf_name}".\n\n'
                            f"Возможные причины:\n"
                            f"1. Книга была перемещена в другую полку\n"
                            f"2. Ошибка кэширования списка книг\n\n"
                            f"Попробуйте:\n"
                            f'1. Нажать "Обновить" для обновления списка\n'
                            f"2. Выбрать другую книгу\n"
                            f"3. Создать новую книгу",
                        )
            except Exception as e:
                self.log_text.append(
                    f'<font color="orange">Предупреждение: не удалось проверить книгу в полке: {e}</font>'
                )
        else:
            # Создаем новую книгу или ищем по имени
            self.log_text.append(
                f'<font color="gray">Создание/поиск книги: {book_name}</font>'
            )
            book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
            if not book_id:
                error_msg = f"Не удалось создать/найти книгу '{book_name}' в полке '{shelf_name}'"
                self.log_text.append(f'<font color="red">{error_msg}</font>')
                return QMessageBox.critical(self, "Ошибка", error_msg)
            self.log_text.append(
                f'<font color="green">Книга найдена/создана: ID {book_id}</font>'
            )

        # Проверка загрузки
        self.log_text.append(f'<font color="#00ffff">ПАРАМЕТРЫ ЗАГРУЗКИ:</font>')
        self.log_text.append(
            f'<font color="gray">- Полка: {shelf_name} (ID: {shelf_id})</font>'
        )
        self.log_text.append(
            f'<font color="gray">- Книга: {book_name} (ID: {book_id})</font>'
        )
        self.log_text.append(
            f'<font color="gray">- Файлов для загрузки: {len(self.converted_files) if isinstance(self.converted_files, list) else sum(len(files) for files in self.converted_files.values())}</font>'
        )

        # ← ГЛАВНОЕ: если только "Без главы" — превращаем в list
        file_groups = self.converted_files
        if (
            isinstance(file_groups, dict)
            and len(file_groups) == 1
            and "Без главы" in file_groups
        ):
            file_groups = file_groups["Без главы"]
            self.log_text.append(
                f'<font color="gray">- Структура: отдельные файлы (без глав)</font>'
            )
        elif isinstance(file_groups, dict):
            self.log_text.append(
                f'<font color="gray">- Структура: с главами ({len(file_groups)} глав)</font>'
            )
        else:
            self.log_text.append(
                f'<font color="gray">- Структура: отдельные файлы</font>'
            )

        self.upload_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat("Инициализация...")

        self.worker = UploadWorker(
            bs_url, headers, book_id, file_groups, self.auto_tags_cb.isChecked()
        )
        self.worker.progress.connect(
            lambda v, s: (self.progress.setValue(v), self.progress.setFormat(s))
        )
        self.worker.log.connect(
            lambda m, c: self.log_text.append(f'<font color="{c}">{m}</font>')
        )
        self.worker.finished.connect(
            lambda s: self.cleanup_upload()
            or QMessageBox.information(
                self, "Готово", f"Загружено: {s} файлов в книгу '{book_name}'"
            )
        )
        self.worker.start()

    def cancel_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        self.cleanup_upload()
        self.log_text.append('<font color="orange">Загрузка отменена</font>')

    def cleanup_upload(self):
        self.upload_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setFormat("Готово")
        self.progress.setValue(100)
