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
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QTextCursor
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
)


class UploadWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(int)

    def __init__(self, base_url, headers, book_id, md_files, auto_tags=True):
        super().__init__()
        self.base_url = base_url
        self.headers = headers
        self.book_id = book_id
        self.md_files = md_files
        self.auto_tags = auto_tags
        self._canceled = False

    def cancel(self):
        self._canceled = True

    def run(self):
        total = len(self.md_files)
        success = 0
        for i, md_path in enumerate(self.md_files):
            if self._canceled:
                break
            self.progress.emit(int(i / total * 100), f"Загрузка: {Path(md_path).name}")
            ok = upload_md_with_images(
                self.base_url,
                self.headers,
                self.book_id,
                md_path,
                log_callback=lambda m, c: self.log.emit(m, c),
                auto_tags=self.auto_tags,
            )
            if ok:
                success += 1
        self.progress.emit(100, f"Готово: {success}/{total}")
        self.finished.emit(success)


class BookStackWidget(QWidget):
    def __init__(self, parent, converted_files, output_folder, project_root):
        super().__init__(parent)
        self.parent_window = parent
        self.converted_files = converted_files
        self.output_folder = output_folder
        self.project_root = Path(project_root)
        self.shelves = []
        self.books = []
        self.worker = None
        self.tagger = SmartTagger()
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
        self.new_shelf_cb.stateChanged.connect(
            lambda s: self.new_shelf_edit.setEnabled(s == Qt.Checked)
        )
        self.new_shelf_edit = QLineEdit("Новая полка")
        self.new_shelf_edit.setEnabled(False)
        self.create_shelf_btn = QPushButton("Создать полку")
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
        self.new_book_cb.stateChanged.connect(
            lambda s: self.new_book_edit.setEnabled(s == Qt.Checked)
        )
        self.new_book_edit = QLineEdit("Новая книга")
        self.new_book_edit.setEnabled(False)
        self.create_book_btn = QPushButton("Создать книгу")
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
        ll.addWidget(self.log_text)
        log_g.setLayout(ll)
        main_layout.addWidget(log_g)

    def create_shelf(self):
        name = self.new_shelf_edit.text().strip()
        if not name:
            return QMessageBox.warning(self, "Ошибка", "Имя полки")
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "URL и токен")
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
            return QMessageBox.warning(self, "Ошибка", "URL и токен")
        headers = {"Authorization": f"Token {token}"}
        shelves = get_shelves(url.rstrip("/"), headers)
        if not shelves:
            return QMessageBox.warning(self, "Ошибка", "Полки не получены")
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

    def update_file_list(self):
        self.file_list.clear()
        for p in self.converted_files:
            item = QListWidgetItem(Path(p).name)
            try:
                tags = self.tagger.get_document_tags(Path(p))
                item.setToolTip("Теги: " + ", ".join(tags))
            except:
                pass
            self.file_list.addItem(item)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Файлы", str(self.project_root), "Markdown (*.md)"
        )
        if files:
            self.converted_files.extend(files)
            self.update_file_list()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка", str(self.project_root))
        if folder:
            self.converted_files.extend(
                [
                    os.path.join(folder, f)
                    for f in os.listdir(folder)
                    if f.endswith(".md")
                ]
            )
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
                self, "Очистить?", "Очистить список?", QMessageBox.Yes | QMessageBox.No
            )
            == QMessageBox.Yes
        ):
            self.converted_files.clear()
            self.update_file_list()

    def show_tag_preview(self):
        if not self.converted_files:
            return QMessageBox.information(self, "Инфо", "Нет файлов")
        preview = "<b>Теги:</b><br><br>"
        for p in self.converted_files:
            tags = self.tagger.get_document_tags(Path(p))
            preview += f"<b>{Path(p).name}</b><br> → {', '.join(tags)}<br><br>"
        dlg = QDialog(self)
        dlg.setWindowTitle("Предпросмотр")
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
            return QMessageBox.warning(self, "Ошибка", "Нет книг")
        text = self.book_combo.currentText()
        name = text.split(" (ID: ")[0]
        book_id = int(text.split("ID: ")[1][:-1])
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "URL и токен")
        tagger = BookStackBookTagger(
            url,
            *token.split(":"),
            log_callback=lambda m, c: self.log_text.append(
                f'<font color="{c}">{m}</font>'
            ),
        )
        if tagger.tag_book(book_id, name):
            QMessageBox.information(self, "Успех", f"Книга «{name}» тегирована")

    def upload_to_bookstack(self):
        url, token = self.url_edit.text().strip(), self.token_edit.text().strip()
        if not all([url, token]):
            return QMessageBox.warning(self, "Ошибка", "URL и токен")
        if not self.converted_files:
            return QMessageBox.warning(self, "Ошибка", "Нет файлов")
        headers = {"Authorization": f"Token {token}"}
        bs_url = url.rstrip("/")

        shelf_name = (
            self.new_shelf_edit.text().strip()
            if self.new_shelf_cb.isChecked()
            else self.shelf_combo.currentText().split(" (")[0]
        )
        shelf_id = create_or_get_shelf(bs_url, headers, shelf_name)
        if not shelf_id:
            return QMessageBox.critical(self, "Ошибка", "Полка")

        book_name = (
            self.new_book_edit.text().strip()
            if self.new_book_cb.isChecked()
            else self.book_combo.currentText().split(" (")[0]
        )
        book_id = create_or_get_book_in_shelf(bs_url, headers, shelf_id, book_name)
        if not book_id:
            return QMessageBox.critical(self, "Ошибка", "Книга")

        self.upload_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.log_text.clear()

        self.worker = UploadWorker(
            bs_url,
            headers,
            book_id,
            self.converted_files,
            self.auto_tags_cb.isChecked(),
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
                    self, "Готово", f"Загружено {s}/{len(self.converted_files)}"
                ),
            )
        )
        self.worker.start()

    def cancel_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        self.cleanup_upload()
        self.log_text.append('<font color="orange">Отменено</font>')

    def cleanup_upload(self):
        self.upload_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setFormat("Готово")
        self.progress.setValue(100)
