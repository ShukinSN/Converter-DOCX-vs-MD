import os
import sys
import subprocess
import tempfile
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
from PyQt5.QtGui import QIcon, QFont, QTextCursor
from converter.converter_thread import EnhancedConverterThread
from gui.preview_window import ModernPreviewWindow
from pathlib import Path
import pypandoc


class DocxToMarkdownConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.preview_window = None
        self.bookstack_window = None
        self.bookstack_btn = None  # Новое: кнопка для BookStack
        self.settings = QSettings("DOCX2MD", "EnhancedConverter")
        self.converted_files = []  # Новое: храним файлы для BookStack
        self.init_ui()
        self.load_settings()
        QTimer.singleShot(100, self.check_pandoc_installation)

    def init_ui(self):
        self.setWindowTitle("DOCX to Markdown Converter")
        self.setGeometry(100, 100, 900, 700)

        # Создаем меню
        menubar = self.menuBar()
        theme_menu = menubar.addMenu("Тема")

        # Действия для тем
        self.dark_theme_action = QAction("Тёмная тема", self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.triggered.connect(lambda: self.change_theme("dark"))

        self.light_theme_action = QAction("Светлая тема", self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.triggered.connect(lambda: self.change_theme("light"))

        # Группа действий для эксклюзивного выбора
        theme_group = QActionGroup(self)
        theme_group.addAction(self.dark_theme_action)
        theme_group.addAction(self.light_theme_action)
        theme_group.setExclusive(True)

        theme_menu.addAction(self.dark_theme_action)
        theme_menu.addAction(self.light_theme_action)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        file_group = QGroupBox("Документы для конвертации")
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)

        btn_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("Добавить файлы")
        self.add_folder_btn = QPushButton("Добавить папку")
        self.remove_btn = QPushButton("Удалить выбранное")
        self.clear_btn = QPushButton("Очистить список")

        btn_layout.addWidget(self.add_files_btn)
        btn_layout.addWidget(self.add_folder_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.clear_btn)

        file_group_layout = QVBoxLayout()
        file_group_layout.addWidget(self.file_list)
        file_group_layout.addLayout(btn_layout)
        file_group.setLayout(file_group_layout)

        settings_group = QGroupBox("Настройки конвертации")
        self.toc_cb = QCheckBox("Генерировать оглавление")
        self.overwrite_cb = QCheckBox("Перезаписывать существующие файлы")
        self.preserve_tabs_cb = QCheckBox("Сохранять табуляцию")
        self.appendix_cb = QCheckBox("Приложение")
        self.bookstack_cb = QCheckBox(
            "Загружать в BookStack после конвертации"
        )  # Вернули чекбокс
        self.appendix_letter_label = QLabel("Буква приложения:")
        self.appendix_letter_edit = QLineEdit()
        self.appendix_letter_edit.setMaxLength(2)
        self.appendix_letter_edit.setFixedWidth(50)
        self.appendix_letter_edit.setEnabled(False)

        # Подключаем обработчики для чекбокса "Приложение"
        self.appendix_cb.stateChanged.connect(self.toggle_appendix_letter)
        self.appendix_cb.stateChanged.connect(self.handle_appendix_toggle)

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.toc_cb)
        settings_layout.addWidget(self.overwrite_cb)
        settings_layout.addWidget(self.preserve_tabs_cb)
        settings_layout.addWidget(self.appendix_cb)
        settings_layout.addWidget(self.bookstack_cb)  # Чекбокс для BookStack

        appendix_letter_layout = QHBoxLayout()
        appendix_letter_layout.addWidget(self.appendix_letter_label)
        appendix_letter_layout.addWidget(self.appendix_letter_edit)
        appendix_letter_layout.addStretch()
        settings_layout.addLayout(appendix_letter_layout)
        settings_group.setLayout(settings_layout)

        output_group = QGroupBox("Папка для сохранения")
        self.output_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Обзор...")
        self.open_folder_btn = QPushButton("Открыть папку")
        self.open_folder_btn.setEnabled(False)

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.browse_btn)
        output_layout.addWidget(self.open_folder_btn)
        output_group.setLayout(output_layout)

        self.convert_btn = QPushButton("Начать конвертацию")
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setEnabled(False)

        # Новое: Кнопка для BookStack (изначально скрыта)
        self.bookstack_btn = QPushButton("Открыть BookStack")
        self.bookstack_btn.clicked.connect(self.open_bookstack_window)
        self.bookstack_btn.setEnabled(False)
        self.bookstack_btn.setVisible(False)

        self.progress = QProgressBar()
        self.progress.setAlignment(Qt.AlignCenter)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))

        layout.addWidget(file_group)
        layout.addWidget(settings_group)
        layout.addWidget(output_group)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.convert_btn)
        btn_row.addWidget(self.bookstack_btn)  # Добавляем кнопку в ряд
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        layout.addWidget(self.progress)
        layout.addWidget(self.log)

        self.add_files_btn.clicked.connect(self.add_files)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.clear_list)
        self.browse_btn.clicked.connect(self.select_output)
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.file_list.itemDoubleClicked.connect(self.preview_file)
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.output_path_edit.textChanged.connect(self.update_open_folder_btn_state)

    def open_bookstack_window(self):
        """Открывает окно BookStack с данными о конвертированных файлах"""
        if self.converted_files:
            from .bookstack_window import BookStackWindow

            project_root = Path(__file__).resolve().parents[2]
            self.bookstack_window = BookStackWindow(
                self,
                self.converted_files,
                self.output_path_edit.text(),
                str(project_root),
            )
            self.bookstack_window.show()
        else:
            QMessageBox.warning(
                self, "Ошибка", "Нет конвертированных файлов для загрузки"
            )

    def change_theme(self, theme_name):
        """Изменяет тему приложения"""
        app = QApplication.instance()

        if theme_name == "dark":
            from .palette import DarkPalette

            DarkPalette.apply(app)
            self.dark_theme_action.setChecked(True)
            self.light_theme_action.setChecked(False)
            self.settings.setValue("theme", "dark")
        elif theme_name == "light":
            from .palette import LightPalette

            LightPalette.apply(app)
            self.light_theme_action.setChecked(True)
            self.dark_theme_action.setChecked(False)
            self.settings.setValue("theme", "light")

    def check_pandoc_installation(self):
        try:
            pypandoc.get_pandoc_version()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Предупреждение",
                f"Pandoc не найден или не установлен.\n\n"
                f"Установите Pandoc с https://pandoc.org/installing.html\n\n"
                f"Ошибка: {str(e)}",
            )

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите DOCX файлы", "", "Word Documents (*.docx)"
        )
        for file in files:
            if file not in [
                self.file_list.item(i).text() for i in range(self.file_list.count())
            ]:
                self.file_list.addItem(file)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(".docx"):
                        file_path = os.path.join(root, file)
                        if file_path not in [
                            self.file_list.item(i).text()
                            for i in range(self.file_list.count())
                        ]:
                            self.file_list.addItem(file_path)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def clear_list(self):
        self.file_list.clear()
        self.converted_files = []  # Очищаем список при очистке

    def select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if folder:
            self.output_path_edit.setText(folder)

    def preview_file(self, item):
        file_path = item.text()
        try:
            with open(file_path, "rb") as f:
                # Простой предпросмотр DOCX (можно улучшить с помощью python-docx)
                content = f.read(1024).decode("utf-8", errors="ignore")
                if self.preview_window:
                    self.preview_window.close()
                self.preview_window = ModernPreviewWindow(self)
                self.preview_window.set_content(content)
                self.preview_window.show()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось прочитать файл: {str(e)}")

    def start_conversion(self):
        if not self.file_list.count():
            QMessageBox.warning(
                self, "Нет файлов", "Добавьте хотя бы один файл для конвертации"
            )
            return

        if not self.output_path_edit.text().strip():
            QMessageBox.warning(
                self, "Не выбрана папка", "Укажите папку для сохранения результатов"
            )
            return

        if not os.path.exists(self.output_path_edit.text()):
            try:
                os.makedirs(self.output_path_edit.text())
            except OSError as e:
                QMessageBox.critical(
                    self, "Ошибка", f"Не удалось создать папку:\n{str(e)}"
                )
                return

        # Показ диалога подтверждения для режима приложения
        if self.appendix_cb.isChecked():
            reply = QMessageBox.question(
                self,
                "Режим приложения",
                "Включён режим Приложение. Продолжить конвертацию?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                self.log.append(
                    "<font color='orange'>Конвертация отменена пользователем</font><br>"
                )
                return

        options = {
            "toc": self.toc_cb.isChecked(),
            "overwrite": self.overwrite_cb.isChecked(),
            "preserve_tabs": self.preserve_tabs_cb.isChecked(),
            "appendix": self.appendix_cb.isChecked(),
            "appendix_letter": self.appendix_letter_edit.text().strip() or "А",
            "bookstack_enable": self.bookstack_cb.isChecked(),  # Флаг для видимости кнопки
        }

        project_root = Path(__file__).resolve().parents[2]

        self.thread = EnhancedConverterThread(
            [self.file_list.item(i).text() for i in range(self.file_list.count())],
            self.output_path_edit.text(),
            options,
            str(project_root),
        )

        self.thread.progress_updated.connect(self.update_progress)
        self.thread.conversion_finished.connect(self.log_result)
        self.thread.finished_all.connect(self.finalize_conversion)
        self.thread.error_occurred.connect(self.log_error)

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.bookstack_btn.setEnabled(False)  # Скрываем кнопку во время конвертации
        self.progress.setValue(0)
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

        if success_count > 0:
            self.converted_files = (
                self.thread.successful_files
            )  # Сохраняем файлы для BookStack
            QMessageBox.information(
                self,
                "Конвертация завершена",
                f"Успешно обработано {success_count} из {total} файлов",
            )
            # Показываем кнопку BookStack, если чекбокс был включён
            if self.bookstack_cb.isChecked():
                self.bookstack_btn.setEnabled(True)
                self.bookstack_btn.setVisible(True)
                self.bookstack_btn.setText(
                    f"Открыть BookStack ({success_count} файлов)"
                )

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
            self.bookstack_btn.setVisible(False)  # Скрываем кнопку при отмене

    def load_settings(self):
        self.output_path_edit.setText(self.settings.value("output_path", ""))
        self.toc_cb.setChecked(self.settings.value("toc", False, type=bool))
        self.overwrite_cb.setChecked(self.settings.value("overwrite", False, type=bool))
        self.preserve_tabs_cb.setChecked(
            self.settings.value("preserve_tabs", False, type=bool)
        )
        self.appendix_cb.setChecked(self.settings.value("appendix", False, type=bool))
        self.bookstack_cb.setChecked(
            self.settings.value("bookstack_enable", False, type=bool)
        )  # Загружаем чекбокс
        self.appendix_letter_edit.setText(self.settings.value("appendix_letter", "А"))

        # Загрузка темы
        theme = self.settings.value("theme", "dark")
        if theme == "light":
            self.change_theme("light")
        else:
            self.change_theme("dark")

        self.update_open_folder_btn_state()

    def save_settings(self):
        self.settings.setValue("output_path", self.output_path_edit.text())
        self.settings.setValue("toc", self.toc_cb.isChecked())
        self.settings.setValue("overwrite", self.overwrite_cb.isChecked())
        self.settings.setValue("preserve_tabs", self.preserve_tabs_cb.isChecked())
        self.settings.setValue("appendix", self.appendix_cb.isChecked())
        self.settings.setValue(
            "bookstack_enable", self.bookstack_cb.isChecked()
        )  # Сохраняем чекбокс
        self.settings.setValue("appendix_letter", self.appendix_letter_edit.text())
        self.settings.setValue("theme", self.settings.value("theme", "dark"))

        if self.output_path_edit.text():
            self.settings.setValue("last_browse_path", self.output_path_edit.text())

    def closeEvent(self, event):
        self.save_settings()
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        if self.preview_window and self.preview_window.isVisible():
            self.preview_window.close()
        if self.bookstack_window and self.bookstack_window.isVisible():
            self.bookstack_window.close()
        event.accept()

    def toggle_appendix_letter(self, state):
        self.appendix_letter_edit.setEnabled(state == Qt.Checked)

    def handle_appendix_toggle(self, state):
        if state == Qt.Checked:
            self.appendix_letter_edit.setFocus()

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
