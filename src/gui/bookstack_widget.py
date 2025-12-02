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
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QCheckBox,
    QFileDialog,
    QTextEdit,
    QProgressBar,
    QStyledItemDelegate,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QIcon, QFont
from pathlib import Path
import os
import resources_rc

from converter.bookstack_api import (
    get_shelves,
    get_books_in_shelf,
    create_or_get_shelf,
    create_or_get_book_in_shelf,
    upload_md_with_images,
    create_or_get_chapter,
    get_book_pages,
    mark_page_as_template,
)
from tagger.smart_tagger import SmartTagger
from tagger.book_tagger import BookStackBookTagger


# Делегат: редактирование только колонки с тегами
class TagsDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 1:
            editor = QLineEdit(parent)
            editor.setPlaceholderText("Введите тег...")
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 1:
            editor.setText(index.data(Qt.EditRole) or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 1:
            model.setData(index, editor.text().strip(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)


# Поток загрузки
class UploadWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(int)

    def __init__(
        self,
        base_url,
        headers,
        book_id,
        file_groups,
        auto_tags=True,
        make_template=False,
        manual_tags=None,
    ):
        super().__init__()
        self.base_url = base_url
        self.headers = headers
        self.book_id = book_id
        self.file_groups = file_groups
        self.auto_tags = auto_tags
        self.make_template = make_template
        self.manual_tags = manual_tags or {}
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        if isinstance(self.file_groups, list):
            total = len(self.file_groups)
            success = 0
            for i, md_path in enumerate(self.file_groups):
                if self._canceled:
                    break
                filename = Path(md_path).name
                self.progress.emit(int((i + 1) / total * 100), f"Загрузка: {filename}")

                manual = self.manual_tags.get(filename, [])
                ok = upload_md_with_images(
                    self.base_url,
                    self.headers,
                    self.book_id,
                    md_path,
                    log_callback=lambda m, c="black": self.log.emit(m, c),
                    chapter_id=None,
                    auto_tags=self.auto_tags and not manual,
                    make_template=self.make_template,
                    manual_tags=manual,
                )
                if ok:
                    success += 1
                self.log.emit(
                    f"{'Успешно' if ok else 'Ошибка'}: {filename}",
                    "green" if ok else "red",
                )

            if not self._canceled:
                self.progress.emit(100, f"Готово: {success}/{total}")
                self.finished.emit(success)
            return

        total = sum(len(files) for files in self.file_groups.values())
        success = processed = 0
        for chapter_name, md_files in self.file_groups.items():
            if self._canceled:
                break
            chapter_id = create_or_get_chapter(
                self.base_url, self.headers, self.book_id, chapter_name
            )
            if not chapter_id:
                self.log.emit(f"Ошибка главы '{chapter_name}'", "red")
                continue
            self.log.emit(f"Глава: {chapter_name}", "orange")

            for md_path in md_files:
                if self._canceled:
                    break
                processed += 1
                filename = Path(md_path).name
                self.progress.emit(
                    int(processed / total * 100), f"{filename} → {chapter_name}"
                )

                manual = self.manual_tags.get(filename, [])
                ok = upload_md_with_images(
                    self.base_url,
                    self.headers,
                    self.book_id,
                    md_path,
                    log_callback=lambda m, c="black": self.log.emit(m, c),
                    chapter_id=chapter_id,
                    auto_tags=self.auto_tags and not manual,
                    make_template=self.make_template,
                    manual_tags=manual,
                )
                if ok:
                    success += 1
                self.log.emit(
                    f"{'Успешно' if ok else 'Ошибка'}: {filename}",
                    "green" if ok else "red",
                )

        if not self._canceled:
            self.progress.emit(100, f"Готово: {success}/{total}")
            self.finished.emit(success)


# Поток шаблонов
class TemplateMarkerWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(int, int)

    def __init__(self, base_url, headers, book_id):
        super().__init__()
        self.base_url = base_url
        self.headers = headers
        self.book_id = book_id
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        pages = get_book_pages(self.base_url, self.headers, self.book_id)
        if not pages:
            self.log.emit("Не удалось получить страницы книги", "red")
            self.finished.emit(0, 0)
            return

        total = len(pages)
        success = 0
        for i, page in enumerate(pages):
            if self._canceled:
                break
            self.progress.emit(
                int((i + 1) / total * 100), f"Обрабатывается: {page['name']}"
            )
            if mark_page_as_template(self.base_url, self.headers, page["id"]):
                success += 1
                self.log.emit(f"Шаблон: {page['name']}", "green")
            else:
                self.log.emit(f"Ошибка: {page['name']}", "red")

        self.progress.emit(100, f"Готово: {success}/{total}")
        self.finished.emit(success, total)


class BookStackWidget(QWidget):
    def __init__(self, parent, converted_files, output_folder, project_root):
        super().__init__(parent)
        self.parent_window = parent
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.shelves = []
        self.books = []
        self.worker = None
        self.template_worker = None
        self.tagger = SmartTagger()
        self.manual_tags_dict = {}

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

        left = QVBoxLayout()
        left.setSpacing(12)

        # Подключение
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

        # Загрузка
        upload_g = QGroupBox("Загрузка")
        ul = QVBoxLayout()

        # Полка
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

        # Книга
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

        # Опции
        options_l = QHBoxLayout()
        self.auto_tags_cb = QCheckBox("Автотегирование")
        self.auto_tags_cb.setChecked(False)
        options_l.addWidget(self.auto_tags_cb)

        self.template_cb = QCheckBox("Создавать как шаблоны")
        options_l.addWidget(self.template_cb)

        hint = QLabel("Теги редактируются двойным кликом в колонке справа")
        hint.setStyleSheet("color: #0066cc; font-weight: bold;")
        options_l.addWidget(hint)
        options_l.addStretch()

        self.preview_btn = QPushButton("Предпросмотр тегов")
        self.preview_btn.clicked.connect(self.show_tag_preview)
        options_l.addWidget(self.preview_btn)

        self.tag_book_btn = QPushButton("Тегировать книгу")
        self.tag_book_btn.clicked.connect(self.tag_current_book)
        self.tag_book_btn.setEnabled(False)
        options_l.addWidget(self.tag_book_btn)
        ul.addLayout(options_l)

        # Кнопка шаблонов
        tmpl_l = QHBoxLayout()
        self.make_templates_btn = QPushButton("Сделать все страницы шаблонами")
        self.make_templates_btn.setEnabled(False)
        self.make_templates_btn.clicked.connect(self.mark_all_pages_as_templates)
        tmpl_l.addWidget(self.make_templates_btn)
        tmpl_l.addStretch()
        ul.addLayout(tmpl_l)

        upload_g.setLayout(ul)
        left.addWidget(upload_g)

        # Файлы и теги — ГЛАВНОЕ УЛУЧШЕНИЕ
        file_g = QGroupBox("Файлы и теги")
        fl = QHBoxLayout()

        self.file_list = QTreeWidget()
        self.file_list.setColumnCount(2)
        self.file_list.setHeaderLabels(["Файл", "Теги (через запятую)"])
        self.file_list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_list.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.file_list.setRootIsDecorated(True)
        self.file_list.setIndentation(20)

        # Только вторая колонка редактируется
        self.file_list.setItemDelegateForColumn(1, TagsDelegate())

        fl.addWidget(self.file_list, 1)

        # Кнопки справа
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

        main_layout.addLayout(left)

        # Нижняя панель
        bl = QHBoxLayout()
        bl.addStretch()
        self.upload_btn = QPushButton("Загрузить в BookStack")
        self.upload_btn.clicked.connect(self.upload_to_bookstack)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_upload)
        self.cancel_btn.setEnabled(False)
        bl.addWidget(self.upload_btn)
        bl.addWidget(self.cancel_btn)
        main_layout.addLayout(bl)

        self.progress = QProgressBar()
        self.progress.setFormat("Готово")
        main_layout.addWidget(self.progress)

        log_g = QGroupBox("Лог")
        ll = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)
        self.log_text.setFont(QFont("Consolas", 9))
        ll.addWidget(self.log_text)
        log_g.setLayout(ll)
        main_layout.addWidget(log_g)

    # Обновление списка
    def update_file_list(self):
        self.file_list.clear()
        if isinstance(self.converted_files, list):
            for p in self.converted_files:
                self._add_file_item(str(p))
        elif isinstance(self.converted_files, dict):
            for chapter_name, files in self.converted_files.items():
                if not files:
                    continue
                chapter_item = QTreeWidgetItem(
                    [f"Глава: {chapter_name} ({len(files)} файлов)", ""]
                )
                chapter_item.setBackground(0, Qt.lightGray)
                chapter_item.setBackground(1, Qt.lightGray)
                chapter_item.setFlags(Qt.ItemIsEnabled)
                self.file_list.addTopLevelItem(chapter_item)
                for p in files:
                    self._add_file_item(str(p), parent=chapter_item)

    def _add_file_item(self, path_str, parent=None):
        path = Path(path_str)
        item = QTreeWidgetItem()
        item.setText(0, path.name)
        item.setData(0, Qt.UserRole, path_str)
        item.setText(1, self.manual_tags_dict.get(path_str, ""))
        item.setFlags(item.flags() | Qt.ItemIsEditable)

        if parent:
            parent.addChild(item)
        else:
            self.file_list.addTopLevelItem(item)

        # Автоматически сохраняем изменения тегов
        self.file_list.itemChanged.connect(self.on_item_changed)

    def on_item_changed(self, item, column):
        if column != 1:
            return
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        tags = item.text(1).strip()
        if tags:
            self.manual_tags_dict[path] = tags
        elif path in self.manual_tags_dict:
            del self.manual_tags_dict[path]

    # Все остальные методы — 100% как у вас были
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
        self.make_templates_btn.setEnabled(bool(books))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать MD", self.last_path, "Markdown (*.md)"
        )
        if not files:
            return
        if files:
            self.last_path = str(Path(files[0]).parent)
            self.save_settings()
        if isinstance(self.converted_files, list):
            self.converted_files.extend(files)
        elif isinstance(self.converted_files, dict):
            if "Без главы" not in self.converted_files:
                self.converted_files["Без главы"] = []
            self.converted_files["Без главы"].extend(files)
        else:
            self.converted_files = files[:]
        self.update_file_list()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку", self.last_path)
        if not folder:
            return
        self.last_path = folder
        self.save_settings()
        folder_path = Path(folder)
        md_files = [
            str(folder_path / f) for f in os.listdir(folder) if f.endswith(".md")
        ]
        if not md_files:
            QMessageBox.information(self, "Пусто", "Нет .md файлов")
            return
        folder_name = folder_path.name
        if not isinstance(self.converted_files, dict):
            self.converted_files = {}
        self.converted_files[folder_name] = md_files
        self.update_file_list()

    def remove_selected(self):
        selected = self.file_list.selectedItems()
        if not selected:
            return
        paths_to_remove = []
        for item in selected:
            path = item.data(0, Qt.UserRole)
            if path:
                paths_to_remove.append(path)

        if isinstance(self.converted_files, list):
            self.converted_files = [
                p for p in self.converted_files if p not in paths_to_remove
            ]
        elif isinstance(self.converted_files, dict):
            for ch in list(self.converted_files.keys()):
                self.converted_files[ch] = [
                    p for p in self.converted_files[ch] if p not in paths_to_remove
                ]
                if not self.converted_files[ch]:
                    del self.converted_files[ch]
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
            self.manual_tags_dict.clear()
            self.update_file_list()

    def save_settings(self):
        self.settings.setValue("bookstack_last_path", self.last_path)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def show_tag_preview(self):
        if not self.converted_files:
            return QMessageBox.information(self, "Инфо", "Нет файлов")
        files = (
            self.converted_files
            if isinstance(self.converted_files, list)
            else [f for fl in self.converted_files.values() for f in fl]
        )
        preview = "<b>Предпросмотр тегов:</b><br><br>"
        for p in files:
            auto = self.tagger.get_document_tags(Path(p))
            manual = (
                self.manual_tags_dict.get(p, "").split(", ")
                if self.manual_tags_dict.get(p)
                else []
            )
            tags = manual or auto
            src = "Ручные" if manual else "Авто"
            preview += f"<b>{Path(p).name}</b> ({src})<br> → {', '.join(tags) if tags else '—'}<br><br>"
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
        if self.book_combo.count() == 0:
            return QMessageBox.warning(self, "Ошибка", "Нет доступных книг")
        text = self.book_combo.currentText()
        name = text.split(" (ID: ")[0]
        book_id = int(text.split("ID: ")[1][:-1])
        url = self.url_edit.text().strip()
        token = self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
        tagger = BookStackBookTagger(url.rstrip("/"), *token.split(":"))
        self.log_text.append(f'<font color="orange">Тегирование книги: «{name}»</font>')
        if tagger.tag_book(book_id, name):
            QMessageBox.information(self, "Успех", f"Книга «{name}» тегирована")
            self.log_text.append(f'<font color="green">Тегирование завершено</font>')
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось тегировать книгу «{name}»")
            self.log_text.append(f'<font color="red">Ошибка тегирования</font>')

    def mark_all_pages_as_templates(self):
        if self.book_combo.count() == 0:
            return QMessageBox.warning(self, "Ошибка", "Выберите книгу")
        text = self.book_combo.currentText()
        book_name = text.split(" (ID: ")[0]
        book_id = int(text.split("ID: ")[1][:-1])

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Сделать ВСЕ страницы книги «{book_name}» шаблонами?\nЭто нельзя отменить массово.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        url = self.url_edit.text().strip().rstrip("/")
        token = self.token_edit.text().strip()
        headers = {"Authorization": f"Token {token}"}

        self.make_templates_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("Помечаем как шаблоны...")
        self.log_text.clear()

        self.template_worker = TemplateMarkerWorker(url, headers, book_id)
        self.template_worker.progress.connect(
            lambda v, s: (self.progress.setValue(v), self.progress.setFormat(s))
        )
        self.template_worker.log.connect(
            lambda m, c: self.log_text.append(f'<font color="{c}">{m}</font>')
        )
        self.template_worker.finished.connect(
            lambda s, t: (
                self.make_templates_btn.setEnabled(True),
                QMessageBox.information(
                    self, "Готово", f"Помечено как шаблоны: {s} из {t}"
                ),
            )
        )
        self.template_worker.start()

    def upload_to_bookstack(self):
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "Укажите URL и токен")
        if not self.converted_files:
            return QMessageBox.warning(self, "Ошибка", "Нет файлов для загрузки")

        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")

        self.log_text.clear()
        self.log_text.append('<font color="#00ffff">=== НАЧАЛО ЗАГРУЗКИ ===</font>')

        # Полка
        shelf_name = (
            self.new_shelf_edit.text().strip()
            if self.new_shelf_cb.isChecked()
            else self.shelf_combo.currentText().split(" (ID: ")[0]
        )
        shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
        if not shelf_id:
            return QMessageBox.critical(self, "Ошибка", f"Полка не найдена/создана")

        # Книга
        book_name = (
            self.new_book_edit.text().strip()
            if self.new_book_cb.isChecked()
            else self.book_combo.currentText().split(" (ID: ")[0]
        )
        book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
        if not book_id:
            return QMessageBox.critical(self, "Ошибка", f"Книга не найдена/создана")

        # Ручные теги
        manual_tags_by_name = {}
        for path, tags_str in self.manual_tags_dict.items():
            filename = Path(path).name
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            if tags:
                manual_tags_by_name[filename] = tags

        file_groups = self.converted_files
        if (
            isinstance(file_groups, dict)
            and len(file_groups) == 1
            and "Без главы" in file_groups
        ):
            file_groups = file_groups["Без главы"]

        self.upload_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)

        self.worker = UploadWorker(
            bs_url,
            headers,
            book_id,
            file_groups,
            auto_tags=self.auto_tags_cb.isChecked(),
            make_template=self.template_cb.isChecked(),
            manual_tags=manual_tags_by_name,
        )
        self.worker.progress.connect(
            lambda v, s: (self.progress.setValue(v), self.progress.setFormat(s))
        )
        self.worker.log.connect(
            lambda m, c: self.log_text.append(f'<font color="{c}">{m}</font>')
        )
        self.worker.finished.connect(
            lambda s: (
                self.cleanup_upload(),
                QMessageBox.information(
                    self, "Готово", f"Успешно загружено: {s} файлов"
                ),
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
        self.progress.setValue(100)
        self.progress.setFormat("Готово")
