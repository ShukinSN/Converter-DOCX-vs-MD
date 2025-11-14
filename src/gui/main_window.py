import os
import sys
import subprocess
import tempfile
import re
import zipfile
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QCheckBox,
    QTabWidget,
    QListWidget,
    QListWidgetItem,
    QAction,
    QActionGroup,
    QMenu,
    QApplication,
)
from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from converter.converter_thread import EnhancedConverterThread
from converter.utils import sanitize_filename
from gui.preview_window import ModernPreviewWindow
from gui.bookstack_widget import BookStackWidget
from tagger.smart_tagger import SmartTagger
from pathlib import Path
import pypandoc


class DocxToMarkdownConverter(QMainWindow):
    """Главное окно приложения для конвертации DOCX в Markdown."""

    def __init__(self):
        super().__init__()
        self.thread = None
        self.preview_window = None
        self.settings = QSettings("DOCX2MD", "EnhancedConverter")
        self.converted_files = {}  # {chapter_name: [md_paths]}
        self.init_ui()
        self.load_settings()
        QTimer.singleShot(100, self.check_pandoc_installation)

    def init_ui(self):
        """Инициализация пользовательского интерфейса."""
        self.setWindowTitle("DOCX to Markdown Converter")
        self.setGeometry(100, 100, 900, 700)

        # === МЕНЮ: ТЕМЫ ===
        menubar = self.menuBar()
        theme_menu = menubar.addMenu("Тема")

        self.dark_theme_action = QAction("Тёмная тема", self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.triggered.connect(lambda: self.change_theme("dark"))

        self.light_theme_action = QAction("Светлая тема", self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.triggered.connect(lambda: self.change_theme("light"))

        theme_group = QActionGroup(self)
        theme_group.addAction(self.dark_theme_action)
        theme_group.addAction(self.light_theme_action)
        theme_group.setExclusive(True)

        theme_menu.addAction(self.dark_theme_action)
        theme_menu.addAction(self.light_theme_action)

        # === ЦЕНТРАЛЬНЫЙ ВИДЖЕТ ===
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # === ВКЛАДКА: КОНВЕРТАЦИЯ ===
        conversion_widget = QWidget()
        conversion_layout = QVBoxLayout(conversion_widget)
        conversion_layout.setSpacing(12)

        # --- Файлы ---
        file_group = QGroupBox("Документы для конвертации")
        file_layout = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        file_layout.addWidget(self.file_list)

        button_layout = QVBoxLayout()
        self.add_files_btn = QPushButton("Добавить файлы")
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn = QPushButton("Добавить папку")
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Очистить список")
        self.clear_btn.clicked.connect(self.clear_list)

        button_layout.addWidget(self.add_files_btn)
        button_layout.addWidget(self.add_folder_btn)
        button_layout.addWidget(self.remove_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        file_layout.addLayout(button_layout)
        file_group.setLayout(file_layout)

        # --- Настройки ---
        settings_group = QGroupBox("Настройки конвертации")
        self.overwrite_cb = QCheckBox("Перезаписывать существующие файлы")
        self.preserve_tabs_cb = QCheckBox("Сохранять табуляцию")
        self.appendix_cb = QCheckBox("Приложение")
        self.appendix_letter_label = QLabel("Буква:")
        self.appendix_letter_edit = QLineEdit()
        self.appendix_letter_edit.setMaxLength(2)
        self.appendix_letter_edit.setFixedWidth(50)
        self.appendix_letter_edit.setEnabled(False)

        self.appendix_cb.stateChanged.connect(self.toggle_appendix_letter)
        self.appendix_cb.stateChanged.connect(self.handle_appendix_toggle)

        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(6)
        settings_layout.addWidget(self.overwrite_cb)
        settings_layout.addWidget(self.preserve_tabs_cb)

        appendix_row = QHBoxLayout()
        appendix_row.setSpacing(6)
        appendix_row.addWidget(self.appendix_cb)
        appendix_row.addWidget(self.appendix_letter_label)
        appendix_row.addWidget(self.appendix_letter_edit)
        appendix_row.addStretch()
        settings_layout.addLayout(appendix_row)
        settings_group.setLayout(settings_layout)

        # --- Папка вывода ---
        output_group = QGroupBox("Папка для сохранения")
        self.output_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Обзор...")
        self.open_folder_btn = QPushButton("Открыть папку")
        self.open_folder_btn.setEnabled(False)

        output_layout = QHBoxLayout()
        output_layout.setSpacing(6)
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.browse_btn)
        output_layout.addWidget(self.open_folder_btn)
        output_group.setLayout(output_layout)

        # --- Кнопки конвертации ---
        convert_buttons_layout = QHBoxLayout()
        convert_buttons_layout.setSpacing(8)
        convert_buttons_layout.addStretch()
        self.convert_btn = QPushButton("Начать конвертацию")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        convert_buttons_layout.addWidget(self.convert_btn)
        convert_buttons_layout.addWidget(self.cancel_btn)

        # --- Прогресс и лог ---
        self.progress = QProgressBar()
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setTextVisible(True)

        log_label = QLabel("Лог:")
        self.log = QTextEdit()
        self.log.setMaximumHeight(150)
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))

        # --- Сигналы ---
        self.browse_btn.clicked.connect(self.browse_output)
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.output_path_edit.textChanged.connect(self.update_open_folder_btn_state)
        self.file_list.itemSelectionChanged.connect(self.on_file_selected)

        # --- Добавляем в layout ---
        conversion_layout.addWidget(file_group)
        conversion_layout.addWidget(settings_group)
        conversion_layout.addWidget(output_group)
        conversion_layout.addLayout(convert_buttons_layout)
        conversion_layout.addWidget(self.progress)
        conversion_layout.addWidget(log_label)
        conversion_layout.addWidget(self.log)

        self.tab_widget.addTab(conversion_widget, "Конвертация")

        # === ВКЛАДКА: BOOKSTACK ===
        self.bookstack_widget = BookStackWidget(
            self,
            self.converted_files,
            self.output_path_edit,
            Path(__file__).parent.parent,
        )
        self.tab_widget.addTab(self.bookstack_widget, "BookStack")

        # По умолчанию — тёмная тема
        self.change_theme("dark")

    # --------------------------------------------------------------------- #
    #   ТЕМЫ
    # --------------------------------------------------------------------- #
    def change_theme(self, theme):
        from gui.palette import DarkPalette, LightPalette

        if theme == "light":
            LightPalette.apply(QApplication.instance())
            self.light_theme_action.setChecked(True)
            self.dark_theme_action.setChecked(False)
        else:
            DarkPalette.apply(QApplication.instance())
            self.dark_theme_action.setChecked(True)
            self.light_theme_action.setChecked(False)
        self.settings.setValue("theme", theme)

    # --------------------------------------------------------------------- #
    #   ДОБАВЛЕНИЕ ФАЙЛОВ / ПАПОК
    # --------------------------------------------------------------------- #
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите DOCX файлы", "", "DOCX Files (*.docx)"
        )
        for file in files:
            if file not in [
                self.file_list.item(i).data(Qt.UserRole)
                for i in range(self.file_list.count())
            ]:
                item = QListWidgetItem(Path(file).name)
                item.setData(Qt.UserRole, file)
                item.setData(Qt.UserRole + 1, None)
                self.file_list.addItem(item)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if not folder:
            return
        base_folder = Path(folder)
        for file_path in base_folder.rglob("*.docx"):
            if str(file_path) not in [
                self.file_list.item(i).data(Qt.UserRole)
                for i in range(self.file_list.count())
            ]:
                item = QListWidgetItem(file_path.name)
                item.setData(Qt.UserRole, str(file_path))
                item.setData(Qt.UserRole + 1, str(base_folder))
                self.file_list.addItem(item)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def clear_list(self):
        self.file_list.clear()

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if folder:
            self.output_path_edit.setText(folder)

    # --------------------------------------------------------------------- #
    #   ПРЕДПРОСМОТР
    # --------------------------------------------------------------------- #
    def on_file_selected(self):
        if not self.file_list.selectedItems():
            return
        selected_item = self.file_list.selectedItems()[0]
        file_path = selected_item.data(Qt.UserRole)
        if self.preview_window:
            self.preview_window.close()
        self.preview_window = ModernPreviewWindow(self)
        try:
            with zipfile.ZipFile(file_path) as z:
                xml = z.read("word/document.xml").decode("utf-8")
                text = " ".join(re.findall(r"<w:t>(.*?)</w:t>", xml, re.DOTALL))[:500]
            self.preview_window.set_content(text)
            self.preview_window.show()
        except Exception as e:
            self.preview_window.set_content(f"Ошибка предпросмотра: {str(e)}")
            self.preview_window.show()

    # --------------------------------------------------------------------- #
    #   КОНВЕРТАЦИЯ
    # --------------------------------------------------------------------- #
    def start_conversion(self):
        if not self.file_list.count():
            QMessageBox.warning(self, "Ошибка", "Нет файлов для конвертации")
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Ошибка", "Укажите папку для сохранения")
            return

        if not os.path.isdir(output_path):
            try:
                os.makedirs(output_path)
            except Exception as e:
                QMessageBox.critical(
                    self, "Ошибка", f"Не удалось создать папку: {str(e)}"
                )
                return

        files_with_bases = [
            (
                self.file_list.item(i).data(Qt.UserRole),
                self.file_list.item(i).data(Qt.UserRole + 1),
            )
            for i in range(self.file_list.count())
        ]

        chapter_groups = {}
        for full_path, base_folder in files_with_bases:
            if full_path and base_folder:
                chapter_name = Path(base_folder).name
                chapter_groups.setdefault(chapter_name, []).append(
                    (full_path, base_folder)
                )
            else:
                chapter_groups.setdefault("NoChapter", []).append(
                    (full_path, base_folder)
                )

        options = {
            "overwrite": self.overwrite_cb.isChecked(),
            "preserve_tabs": self.preserve_tabs_cb.isChecked(),
            "toc": False,
            "appendix": self.appendix_cb.isChecked(),
            "appendix_letter": (
                self.appendix_letter_edit.text().upper()
                if self.appendix_cb.isChecked()
                else "А"
            ),
        }

        self.thread = EnhancedConverterThread(
            files_with_bases, output_path, options, Path(__file__).parent.parent
        )
        self.thread.chapter_groups = chapter_groups
        self.thread.progress_updated.connect(self.update_progress)
        self.thread.conversion_finished.connect(self.log_result)
        self.thread.finished_all.connect(self.finalize_conversion)
        self.thread.error_occurred.connect(self.log_error)

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat("Инициализация...")
        self.log.clear()

        self.thread.start()

    def update_progress(self, value, filename):
        self.progress.setValue(value)
        self.progress.setFormat(f"{filename} — {value}%")

    def log_result(self, filename, message, output_path):
        if output_path:
            self.log.append(f"<font color='green'>{message}</font>")
            self.log.append(f"<font color='gray'>Сохранено в: {output_path}</font><br>")
        else:
            self.log.append(f"<font color='red'>{message}</font><br>")
        self.log.moveCursor(QTextCursor.End)

    def log_error(self, message):
        self.log.append(f"<font color='red'>{message}</font><br>")
        self.log.moveCursor(QTextCursor.End)

    def finalize_conversion(self, success_count):
        total = self.file_list.count()
        self.progress.setFormat(f"Готово! Успешно: {success_count}/{total}")
        self.progress.setValue(100)
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if success_count == 0:
            return

        self.converted_files = {}
        output_root = Path(self.output_path_edit.text())

        # Проверяем: есть ли хоть одна папка в списке?
        has_folders = any(
            self.file_list.item(i).data(Qt.UserRole + 1) is not None
            for i in range(self.file_list.count())
        )

        for chapter_name, files in self.thread.chapter_groups.items():
            md_paths = []
            for fp in files:
                input_path = Path(fp[0])
                base_folder = Path(fp[1]) if fp[1] else None

                # Определяем относительную папку
                rel_dir = Path()
                if base_folder and input_path.parent != base_folder:
                    rel_dir = input_path.parent.relative_to(base_folder)

                md_path = (
                    output_root / rel_dir / f"{sanitize_filename(input_path.stem)}.md"
                )
                if md_path.exists():
                    md_paths.append(str(md_path))

            if not md_paths:
                continue

            # === КЛЮЧЕВАЯ ЛОГИКА ===
            if has_folders:
                # Используем имена папок как главы
                real_chapter_name = (
                    chapter_name if chapter_name != "NoChapter" else "Без главы"
                )
                self.converted_files[real_chapter_name] = md_paths
            else:
                # Если добавлены только отдельные файлы — НЕ создаём главы!
                # Всё идёт в корень книги → просто список файлов
                self.converted_files = md_paths  # ← СПИСОК, а не dict!
                break  # Больше ничего не добавляем
        else:
            # Если has_folders == False и мы не вошли в break
            if not has_folders and self.converted_files == {}:
                # Все файлы — отдельные, без папок
                all_md_paths = []
                for i in range(self.file_list.count()):
                    full_path = self.file_list.item(i).data(Qt.UserRole)
                    if full_path:
                        input_path = Path(full_path)
                        md_path = (
                            output_root / f"{sanitize_filename(input_path.stem)}.md"
                        )
                        if md_path.exists():
                            all_md_paths.append(str(md_path))
                self.converted_files = all_md_paths  # ← СПИСОК

        # Обновляем BookStack
        self.bookstack_widget.converted_files = self.converted_files
        self.bookstack_widget.update_file_list()

        QMessageBox.information(self, "Готово", f"Успешно: {success_count}/{total}")

    def cancel_conversion(self):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
            self.log.append(
                "<font color='orange'>Конвертация отменена пользователем</font><br>"
            )
            self.progress.setFormat("Отменено")
            self.progress.setValue(0)
            self.convert_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)

    # --------------------------------------------------------------------- #
    #   НАСТРОЙКИ
    # --------------------------------------------------------------------- #
    def load_settings(self):
        self.output_path_edit.setText(self.settings.value("output_path", ""))
        self.overwrite_cb.setChecked(self.settings.value("overwrite", False, type=bool))
        self.preserve_tabs_cb.setChecked(
            self.settings.value("preserve_tabs", False, type=bool)
        )
        self.appendix_cb.setChecked(self.settings.value("appendix", False, type=bool))
        self.appendix_letter_edit.setText(self.settings.value("appendix_letter", "А"))
        self.update_open_folder_btn_state()

        theme = self.settings.value("theme", "dark")
        self.change_theme(theme)

    def save_settings(self):
        self.settings.setValue("output_path", self.output_path_edit.text())
        self.settings.setValue("overwrite", self.overwrite_cb.isChecked())
        self.settings.setValue("preserve_tabs", self.preserve_tabs_cb.isChecked())
        self.settings.setValue("appendix", self.appendix_cb.isChecked())
        self.settings.setValue("appendix_letter", self.appendix_letter_edit.text())
        self.settings.setValue("theme", self.settings.value("theme", "dark"))

    def closeEvent(self, event):
        self.save_settings()
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        if self.preview_window and self.preview_window.isVisible():
            self.preview_window.close()
        event.accept()

    # --------------------------------------------------------------------- #
    #   ПРИЛОЖЕНИЕ
    # --------------------------------------------------------------------- #
    def toggle_appendix_letter(self, state):
        self.appendix_letter_edit.setEnabled(state == Qt.Checked)

    def handle_appendix_toggle(self, state):
        if state == Qt.Checked:
            self.appendix_letter_edit.setFocus()

    # --------------------------------------------------------------------- #
    #   ПАПКА ВЫВОДА
    # --------------------------------------------------------------------- #
    def update_open_folder_btn_state(self):
        path = self.output_path_edit.text()
        self.open_folder_btn.setEnabled(bool(path.strip() and os.path.isdir(path)))

    def open_output_folder(self):
        path = self.output_path_edit.text()
        if os.path.isdir(path):
            try:
                if os.name == "nt":
                    os.startfile(path)
                elif os.name == "posix":
                    if sys.platform == "darwin":
                        subprocess.Popen(["open", path])
                    else:
                        subprocess.Popen(["xdg-open", path])
            except Exception as e:
                QMessageBox.warning(
                    self, "Ошибка", f"Не удалось открыть папку:\n{str(e)}"
                )
        else:
            QMessageBox.warning(self, "Ошибка", "Указанная папка не существует")

    # --------------------------------------------------------------------- #
    #   ПРОВЕРКА PANDOC
    # --------------------------------------------------------------------- #
    def check_pandoc_installation(self):
        try:
            version = pypandoc.get_pandoc_version()
            if tuple(map(int, version.split("."))) < (2, 14):
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    f"Найдена версия Pandoc {version}. Рекомендуется 2.14 или выше.",
                )
        except Exception:
            QMessageBox.critical(
                self,
                "Ошибка",
                "Pandoc не установлен или не найден в PATH. Установите с https://pandoc.org/installing.html",
            )
