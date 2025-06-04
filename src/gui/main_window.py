import os
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
)
from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QIcon, QFont, QTextCursor

# from src.converter.converter_thread import EnhancedConverterThread
from converter.converter_thread import EnhancedConverterThread

# from src.gui.preview_window import ModernPreviewWindow
import pypandoc

from gui.preview_window import ModernPreviewWindow


class DocxToMarkdownConverter(
    QMainWindow
):  # Главное окно приложения с современным интерфейсом.
    def __init__(self):
        super().__init__()
        self.thread = None
        self.preview_window = None
        self.settings = QSettings("DOCX2MD", "EnhancedConverter")
        self.init_ui()
        self.load_settings()
        QTimer.singleShot(100, self.check_pandoc_installation)

    def init_ui(self):  # Инициализация пользовательского интерфейса.
        self.setWindowTitle("DOCX to Markdown Converter Pro")
        self.setGeometry(100, 100, 900, 700)

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
        self.smart_quotes_cb = QCheckBox("Умные кавычки")
        self.preserve_tabs_cb = QCheckBox("Сохранять табуляцию")

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.toc_cb)
        settings_layout.addWidget(self.overwrite_cb)
        settings_layout.addWidget(self.smart_quotes_cb)
        settings_layout.addWidget(self.preserve_tabs_cb)
        settings_group.setLayout(settings_layout)

        output_group = QGroupBox("Папка для сохранения")
        self.output_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Обзор...")

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(self.browse_btn)
        output_group.setLayout(output_layout)

        self.convert_btn = QPushButton("Начать конвертацию")
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setEnabled(False)

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

    def check_pandoc_installation(self):  # Проверка наличия Pandoc.

        try:
            pypandoc.get_pandoc_version()
        except OSError:
            QMessageBox.critical(
                self,
                "Pandoc не найден",
                "Для работы программы требуется Pandoc.\n\n"
                "Установите его с официального сайта: https://pandoc.org/installing.html",
            )

    def add_files(self):  # Добавление файлов через диалог.

        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите DOCX файлы", "", "Документы Word (*.docx);;Все файлы (*)"
        )

        if files:
            existing = {
                self.file_list.item(i).text() for i in range(self.file_list.count())
            }
            for f in files:
                if f not in existing:
                    item = QListWidgetItem(f)
                    item.setToolTip(f)
                    self.file_list.addItem(item)

    def add_folder(self):  # Добавление всех DOCX из папки.

        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с документами")
        if folder:
            existing = {
                self.file_list.item(i).text() for i in range(self.file_list.count())
            }
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".docx"):
                        path = os.path.join(root, f)
                        if path not in existing:
                            item = QListWidgetItem(path)
                            item.setToolTip(path)
                            self.file_list.addItem(item)

    def remove_selected(self):  # Удаление выбранных файлов из списка.

        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def clear_list(self):  # Очистка всего списка файлов.

        self.file_list.clear()

    def select_output(self):  # Выбор папки для сохранения.

        path = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if path:
            self.output_path_edit.setText(path)

    def preview_file(self, item):  # редпросмотр выбранного файла.

        if self.preview_window is None:
            self.preview_window = ModernPreviewWindow(self)

        try:
            content = pypandoc.convert_file(
                item.text(), "markdown", format="docx", extra_args=["--wrap=none"]
            )
            self.preview_window.set_content(content)
            self.preview_window.show()
        except Exception as e:
            QMessageBox.warning(
                self, "Ошибка предпросмотра", f"Не удалось открыть файл:\n{str(e)}"
            )

    def start_conversion(self):  # Запуск процесса конвертации.

        if self.file_list.count() == 0:
            QMessageBox.warning(self, "Нет файлов", "Добавьте файлы для конвертации")
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

        options = {
            "toc": self.toc_cb.isChecked(),
            "overwrite": self.overwrite_cb.isChecked(),
            "smart": self.smart_quotes_cb.isChecked(),
            "preserve_tabs": self.preserve_tabs_cb.isChecked(),
        }

        self.thread = EnhancedConverterThread(
            [self.file_list.item(i).text() for i in range(self.file_list.count())],
            self.output_path_edit.text(),
            options,
        )

        self.thread.progress_updated.connect(self.update_progress)
        self.thread.conversion_finished.connect(self.log_result)
        self.thread.finished_all.connect(self.finalize_conversion)
        self.thread.error_occurred.connect(self.log_error)

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.log.clear()

        self.thread.start()

    def update_progress(self, value, filename):  # Oбновление прогресс-бара.

        self.progress.setValue(value)
        self.progress.setFormat(f"{filename} — {value}%")

    def log_result(self, filename, message, output_path):  # Логирование результата.

        if output_path:
            self.log.append(f"<font color='green'>{message}</font>")
            self.log.append(f"<font color='gray'>Сохранено в: {output_path}</font><br>")
        else:
            self.log.append(f"<font color='red'>{message}</font><br>")

        self.log.moveCursor(QTextCursor.End)

    def log_error(self, message):  # Логирование ошибки.

        self.log.append(f"<font color='red'>{message}</font><br>")
        self.log.moveCursor(QTextCursor.End)

    def finalize_conversion(self, success_count):  # Завершение процесса конвертации.

        total = self.file_list.count()
        self.progress.setFormat(f"Готово! Успешно: {success_count}/{total}")
        self.progress.setValue(100)

        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if success_count > 0:
            QMessageBox.information(
                self,
                "Конвертация завершена",
                f"Успешно обработано {success_count} из {total} файлов",
            )

    def cancel_conversion(self):  # Отмена конвертации.

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

    def load_settings(self):  # Загрузка сохраненных настроек.

        self.output_path_edit.setText(self.settings.value("output_path", ""))
        self.toc_cb.setChecked(self.settings.value("toc", False, type=bool))
        self.overwrite_cb.setChecked(self.settings.value("overwrite", False, type=bool))
        self.smart_quotes_cb.setChecked(
            self.settings.value("smart_quotes", True, type=bool)
        )
        self.preserve_tabs_cb.setChecked(
            self.settings.value("preserve_tabs", False, type=bool)
        )

    def save_settings(self):  # Сохранение текущих настроек.

        self.settings.setValue("output_path", self.output_path_edit.text())
        self.settings.setValue("toc", self.toc_cb.isChecked())
        self.settings.setValue("overwrite", self.overwrite_cb.isChecked())
        self.settings.setValue("smart_quotes", self.smart_quotes_cb.isChecked())
        self.settings.setValue("preserve_tabs", self.preserve_tabs_cb.isChecked())

    def closeEvent(self, event):  # Обработка закрытия окна.

        self.save_settings()
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        event.accept()
