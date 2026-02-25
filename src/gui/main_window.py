import os
import sys
import subprocess
import re
import zipfile
from pathlib import Path

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAction,
    QActionGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from converter.converter_thread import EnhancedConverterThread
from converter.utils import sanitize_filename
from gui.bookstack_widget import BookStackWidget
import pypandoc


class DocxToMarkdownConverter(QMainWindow):
    """Главное окно приложения для конвертации DOCX в Markdown."""

    def __init__(self):
        super().__init__()
        self.thread = None
        self.settings = QSettings("DOCX2MD", "EnhancedConverter")
        self.converted_files = {}  # {chapter_name: [md_paths]}

        self.init_ui()
        self.load_settings()
        QTimer.singleShot(100, self.check_pandoc_installation)

    # --------------------------------------------------------------------- #
    #   Инициализация интерфейса
    # --------------------------------------------------------------------- #
    def init_ui(self):
        self.setWindowTitle("DOCX to Markdown Converter")
        self.setGeometry(100, 100, 1150, 700)

        # === Меню: Темы ===
        menubar = self.menuBar()
        theme_menu = menubar.addMenu("Тема")

        self.dark_theme_action = QAction("Тёмная тема", self, checkable=True)
        self.dark_theme_action.triggered.connect(lambda: self.change_theme("dark"))

        self.light_theme_action = QAction("Светлая тема", self, checkable=True)
        self.light_theme_action.triggered.connect(lambda: self.change_theme("light"))

        theme_group = QActionGroup(self)
        theme_group.addAction(self.dark_theme_action)
        theme_group.addAction(self.light_theme_action)
        theme_group.setExclusive(True)

        theme_menu.addAction(self.dark_theme_action)
        theme_menu.addAction(self.light_theme_action)

        # === Центральный виджет ===
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # === Вкладка: Конвертация ===
        conversion_tab = QWidget()
        conv_layout = QVBoxLayout(conversion_tab)
        conv_layout.setSpacing(12)

        # --- Группа: Документы для конвертации ---
        files_group = QGroupBox("Документы для конвертации")
        files_main_layout = QHBoxLayout()
        files_main_layout.setSpacing(12)

        # Таблица файлов
        files_table_layout = QVBoxLayout()
        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(
            ["", "Заголовок", "Приложение", "Буква"]
        )
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.file_table.setColumnWidth(0, 30)
        self.file_table.setColumnWidth(2, 80)
        self.file_table.setColumnWidth(3, 60)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        files_table_layout.addWidget(self.file_table)
        files_main_layout.addLayout(files_table_layout, stretch=1)

        # Кнопки управления (справа, в столбик)
        buttons_column = QVBoxLayout()
        buttons_column.setSpacing(8)

        self.add_files_btn = QPushButton("Добавить файлы")
        self.add_files_btn.clicked.connect(self.add_files)

        self.add_folder_btn = QPushButton("Добавить папку")
        self.add_folder_btn.clicked.connect(self.add_folder)

        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self.remove_selected)

        self.clear_btn = QPushButton("Очистить список")
        self.clear_btn.clicked.connect(self.clear_list)

        for btn in (
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
        ):
            buttons_column.addWidget(btn)

        buttons_column.addStretch()
        files_main_layout.addLayout(buttons_column, stretch=0)
        files_group.setLayout(files_main_layout)

        # --- Группа: Настройки конвертации ---
        settings_group = QGroupBox("Настройки конвертации")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(6)

        self.overwrite_cb = QCheckBox("Перезаписывать существующие файлы")
        self.preserve_tabs_cb = QCheckBox("Сохранять табуляцию")

        settings_layout.addWidget(self.overwrite_cb)
        settings_layout.addWidget(self.preserve_tabs_cb)
        settings_group.setLayout(settings_layout)

        # --- Группа: Папка вывода ---
        output_group = QGroupBox("Папка для сохранения")
        output_layout = QHBoxLayout()
        output_layout.setSpacing(6)

        self.output_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Обзор...")
        self.open_folder_btn = QPushButton("Открыть папку")
        self.open_folder_btn.setEnabled(False)

        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.browse_btn)
        output_layout.addWidget(self.open_folder_btn)
        output_group.setLayout(output_layout)

        # --- Кнопки конвертации ---
        convert_btns_layout = QHBoxLayout()
        convert_btns_layout.addStretch()
        self.convert_btn = QPushButton("Начать конвертацию")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        convert_btns_layout.addWidget(self.convert_btn)
        convert_btns_layout.addWidget(self.cancel_btn)

        # --- Прогресс и лог ---
        self.progress = QProgressBar()
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setTextVisible(True)

        log_label = QLabel("Лог:")
        self.log = QTextEdit()
        self.log.setMaximumHeight(150)
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))

        # --- Подключение сигналов ---
        self.browse_btn.clicked.connect(self.browse_output)
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.output_path_edit.textChanged.connect(self.update_open_folder_btn_state)
        self.file_table.itemChanged.connect(self.on_item_changed)

        # --- Добавление в layout ---
        conv_layout.addWidget(files_group)
        conv_layout.addWidget(settings_group)
        conv_layout.addWidget(output_group)
        conv_layout.addLayout(convert_btns_layout)
        conv_layout.addWidget(self.progress)
        conv_layout.addWidget(log_label)
        conv_layout.addWidget(self.log)

        self.tab_widget.addTab(conversion_tab, "Конвертация")

        # === Вкладка: BookStack ===
        self.bookstack_widget = BookStackWidget(
            self,
            self.converted_files,
            self.output_path_edit,
            Path(__file__).parent.parent,
        )
        self.tab_widget.addTab(self.bookstack_widget, "BookStack")

        # По умолчанию — тёмная тема
        self.change_theme("dark")

    # ===================================================================== #
    #   Добавление файлов и папок с естественной сортировкой
    # ===================================================================== #

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите DOCX файлы", "", "DOCX Files (*.docx)"
        )
        added = False
        for file in files:
            if not self.file_exists_in_table(file):
                self.add_file_row(file, None)
                added = True

        if added:
            self._sort_table_naturally()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if not folder:
            return

        folder_path = Path(folder)
        docx_files = list(folder_path.glob("*.docx"))

        # === ЕСТЕСТВЕННАЯ СОРТИРОВКА ===
        def natural_sort_key(p: Path):
            return [
                int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)
            ]

        docx_files.sort(key=natural_sort_key)

        added = False
        for file in docx_files:
            file_str = str(file)
            if not self.file_exists_in_table(file_str):
                self.add_file_row(file_str, str(folder_path))
                added = True

        if added:
            self._sort_table_naturally()

    def file_exists_in_table(self, file_path: str) -> bool:
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 1)
            if item and item.data(Qt.UserRole) == file_path:
                return True
        return False

    def add_file_row(self, file_path: str, base_folder: str | None):
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)

        # 0: Чекбокс удаления
        del_cb = QTableWidgetItem()
        del_cb.setCheckState(Qt.Unchecked)
        del_cb.setData(Qt.UserRole, file_path)
        self.file_table.setItem(row, 0, del_cb)

        # 1: Имя файла
        name_item = QTableWidgetItem(Path(file_path).name)
        name_item.setData(Qt.UserRole, file_path)
        name_item.setData(Qt.UserRole + 1, base_folder)
        self.file_table.setItem(row, 1, name_item)

        # 2: Чекбокс "Приложение"
        app_cb = QTableWidgetItem()
        app_cb.setCheckState(Qt.Unchecked)
        app_cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        self.file_table.setItem(row, 2, app_cb)

        # 3: Поле буквы
        letter_edit = QLineEdit()
        letter_edit.setMaxLength(2)
        letter_edit.setFixedWidth(50)
        letter_edit.setEnabled(False)
        letter_edit.setText("А")
        # Подключаем сигнал с передачей строки
        letter_edit.textChanged.connect(
            lambda text, r=row: self.on_letter_changed(r, text)
        )
        self.file_table.setCellWidget(row, 3, letter_edit)

    def _sort_table_naturally(self):
        """Полная пересортировка таблицы по естественному порядку имён файлов"""
        rows = []
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 1)
            if not name_item:
                continue

            filename = name_item.text()
            file_path = name_item.data(Qt.UserRole)
            base_folder = name_item.data(Qt.UserRole + 1)

            app_item = self.file_table.item(row, 2)
            is_app = app_item.checkState() == Qt.Checked if app_item else False

            letter = "А"
            if is_app:
                letter_widget = self.file_table.cellWidget(row, 3)
                if letter_widget:
                    letter = letter_widget.text().strip().upper() or "А"

            rows.append((filename, file_path, base_folder, is_app, letter))

        # Естественная сортировка
        def natural_key(tup):
            return [
                int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", tup[0])
            ]

        rows.sort(key=natural_key)

        # Перезаполняем таблицу
        self.file_table.setRowCount(0)
        for filename, file_path, base_folder, is_app, letter in rows:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            # Чекбокс удаления
            del_cb = QTableWidgetItem()
            del_cb.setCheckState(Qt.Unchecked)
            del_cb.setData(Qt.UserRole, file_path)
            self.file_table.setItem(row, 0, del_cb)

            # Имя файла
            name_item = QTableWidgetItem(filename)
            name_item.setData(Qt.UserRole, file_path)
            name_item.setData(Qt.UserRole + 1, base_folder)
            self.file_table.setItem(row, 1, name_item)

            # Приложение
            app_cb = QTableWidgetItem()
            app_cb.setCheckState(Qt.Checked if is_app else Qt.Unchecked)
            app_cb.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self.file_table.setItem(row, 2, app_cb)

            # Буква
            letter_edit = QLineEdit()
            letter_edit.setMaxLength(2)
            letter_edit.setFixedWidth(50)
            letter_edit.setEnabled(is_app)
            letter_edit.setText(letter)
            letter_edit.textChanged.connect(
                lambda text, r=row: self.on_letter_changed(r, text)
            )
            self.file_table.setCellWidget(row, 3, letter_edit)

    # --------------------------------------------------------------------- #
    #   Обработчики чекбоксов и полей
    # --------------------------------------------------------------------- #
    def on_item_changed(self, item):
        if item.column() == 2:  # Чекбокс "Приложение"
            row = item.row()
            enabled = item.checkState() == Qt.Checked
            letter_edit = self.file_table.cellWidget(row, 3)
            if letter_edit:
                letter_edit.setEnabled(enabled)
                if enabled and not letter_edit.text().strip():
                    letter_edit.setText("А")

    def on_letter_changed(self, row: int, text: str):
        letter_edit = self.file_table.cellWidget(row, 3)
        if letter_edit:
            cleaned = text.strip().upper()[:2]
            if cleaned != text:
                letter_edit.setText(cleaned)

    # --------------------------------------------------------------------- #
    #   Удаление и очистка
    # --------------------------------------------------------------------- #
    def remove_selected(self):
        rows_to_remove = [
            row
            for row in range(self.file_table.rowCount())
            if self.file_table.item(row, 0).checkState() == Qt.Checked
        ]
        for row in sorted(rows_to_remove, reverse=True):
            self.file_table.removeRow(row)

    def clear_list(self):
        self.file_table.setRowCount(0)

    # --------------------------------------------------------------------- #
    #   Конвертация
    # --------------------------------------------------------------------- #
    def start_conversion(self):
        if self.file_table.rowCount() == 0:
            QMessageBox.warning(self, "Ошибка", "Нет файлов для конвертации")
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Ошибка", "Укажите папку для сохранения")
            return

        os.makedirs(output_path, exist_ok=True)

        files_with_meta = []
        chapter_groups = {}

        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 1)
            app_item = self.file_table.item(row, 2)
            letter_widget = self.file_table.cellWidget(row, 3)

            file_path = name_item.data(Qt.UserRole)
            base_folder = name_item.data(Qt.UserRole + 1)
            is_appendix = app_item.checkState() == Qt.Checked
            appendix_letter = letter_widget.text().upper() if is_appendix else "А"

            meta = (file_path, base_folder, is_appendix, appendix_letter)
            files_with_meta.append(meta)

            chapter_name = Path(base_folder).name if base_folder else "NoChapter"
            chapter_groups.setdefault(chapter_name, []).append(meta)

        options = {
            "overwrite": self.overwrite_cb.isChecked(),
            "preserve_tabs": self.preserve_tabs_cb.isChecked(),
            "toc": False,
            "appendix": False,
        }

        self.thread = EnhancedConverterThread(
            files_with_meta, output_path, options, Path(__file__).parent.parent
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

    def update_progress(self, value: int, filename: str):
        self.progress.setValue(value)
        self.progress.setFormat(f"{filename} — {value}%")

    def log_result(self, filename: str, message: str, output_path: str | None):
        color = "green" if output_path else "red"
        self.log.append(f"<font color='{color}'>{message}</font>")
        if output_path:
            self.log.append(f"<font color='gray'>Сохранено в: {output_path}</font><br>")
        else:
            self.log.append("<br>")
        self.log.moveCursor(QTextCursor.End)

    def log_error(self, message: str):
        self.log.append(f"<font color='red'>{message}</font><br>")
        self.log.moveCursor(QTextCursor.End)

    def finalize_conversion(self, success_count: int):
        total = self.file_table.rowCount()
        self.progress.setFormat(f"Готово! Успешно: {success_count}/{total}")
        self.progress.setValue(100)
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if success_count == 0:
            return

        output_root = Path(self.output_path_edit.text())
        has_folders = any(
            self.file_table.item(r, 1).data(Qt.UserRole + 1) is not None
            for r in range(self.file_table.rowCount())
        )

        self.converted_files = {}
        for chapter_name, files in self.thread.chapter_groups.items():
            md_paths = []
            for file_path, base_folder, _, _ in files:
                input_path = Path(file_path)
                rel_dir = Path()
                if base_folder and input_path.parent != Path(base_folder):
                    try:
                        rel_dir = input_path.parent.relative_to(base_folder)
                    except ValueError:
                        pass
                md_path = (
                    output_root / rel_dir / f"{sanitize_filename(input_path.stem)}.md"
                )
                if md_path.exists():
                    md_paths.append(str(md_path))

            if not md_paths:
                continue

            name = chapter_name if chapter_name != "NoChapter" else "Без главы"
            self.converted_files[name] = md_paths

        # Если нет папок — просто список файлов
        if not has_folders and len(self.converted_files) == 1:
            self.converted_files = list(self.converted_files.values())[0]

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
    #   Настройки, темы, папка вывода
    # --------------------------------------------------------------------- #
    def change_theme(self, theme: str):
        from gui.palette import DarkPalette, LightPalette

        palette = LightPalette if theme == "light" else DarkPalette
        palette.apply(QApplication.instance())

        self.light_theme_action.setChecked(theme == "light")
        self.dark_theme_action.setChecked(theme == "dark")
        self.settings.setValue("theme", theme)

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if folder:
            self.output_path_edit.setText(folder)

    def load_settings(self):
        self.output_path_edit.setText(self.settings.value("output_path", ""))
        self.overwrite_cb.setChecked(self.settings.value("overwrite", False, bool))
        self.preserve_tabs_cb.setChecked(
            self.settings.value("preserve_tabs", False, bool)
        )
        self.update_open_folder_btn_state()
        self.change_theme(self.settings.value("theme", "dark"))

    def save_settings(self):
        self.settings.setValue("output_path", self.output_path_edit.text())
        self.settings.setValue("overwrite", self.overwrite_cb.isChecked())
        self.settings.setValue("preserve_tabs", self.preserve_tabs_cb.isChecked())
        self.settings.setValue(
            "theme", "dark" if self.dark_theme_action.isChecked() else "light"
        )

    def closeEvent(self, event):
        self.save_settings()
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        event.accept()

    def update_open_folder_btn_state(self):
        path = self.output_path_edit.text()
        self.open_folder_btn.setEnabled(bool(path.strip() and os.path.isdir(path)))

    def open_output_folder(self):
        path = self.output_path_edit.text()
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Ошибка", "Указанная папка не существует")
            return

        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{str(e)}")

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
                "Pandoc не установлен или не найден в PATH.\n"
                "Установите с https://pandoc.org/installing.html",
            )
