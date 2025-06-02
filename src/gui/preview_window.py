from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QTabWidget,
    QMessageBox,
    QFileDialog,
)
from PyQt5.QtGui import QFont
import markdown


class ModernPreviewWindow(QWidget):
    """Современное окно предпросмотра с подсветкой синтаксиса."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр Markdown")
        self.setGeometry(300, 300, 900, 700)

        layout = QVBoxLayout()
        self.tabs = QTabWidget()

        self.raw_edit = QTextEdit()
        self.raw_edit.setFont(QFont("Consolas", 10))

        self.rendered_view = QTextEdit()
        self.rendered_view.setReadOnly(True)
        self.rendered_view.setFont(QFont("Segoe UI", 10))

        self.tabs.addTab(self.raw_edit, "Markdown")
        self.tabs.addTab(self.rendered_view, "HTML Preview")

        btn_layout = QHBoxLayout()
        self.copy_md_btn = QPushButton("Копировать Markdown")
        self.copy_html_btn = QPushButton("Копировать HTML")
        self.save_btn = QPushButton("Сохранить как...")
        self.close_btn = QPushButton("Закрыть")

        btn_layout.addWidget(self.copy_md_btn)
        btn_layout.addWidget(self.copy_html_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.close_btn)

        layout.addWidget(self.tabs)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.copy_md_btn.clicked.connect(self.copy_markdown)
        self.copy_html_btn.clicked.connect(self.copy_html)
        self.save_btn.clicked.connect(self.save_content)
        self.close_btn.clicked.connect(self.close)

    def set_content(self, text):
        """Установка содержимого для предпросмотра."""
        self.raw_edit.setPlainText(text)
        html = markdown.markdown(text, extensions=["fenced_code", "codehilite"])
        self.rendered_view.setHtml(f"{html}")

    def copy_markdown(self):
        """Копирование Markdown в буфер обмена."""
        clipboard = self.parent().QApplication.clipboard()
        clipboard.setText(self.raw_edit.toPlainText())
        QMessageBox.information(
            self, "Скопировано", "Markdown скопирован в буфер обмена"
        )

    def copy_html(self):
        """Копирование HTML в буфер обмена."""
        clipboard = self.parent().QApplication.clipboard()
        clipboard.setText(self.rendered_view.toHtml())
        QMessageBox.information(self, "Скопировано", "HTML скопирован в буфер обмена")

    def save_content(self):
        """Сохранение содержимого в файл."""
        formats = {
            "Markdown (*.md)": lambda: self.raw_edit.toPlainText(),
            "HTML (*.html)": lambda: self.rendered_view.toHtml(),
        }

        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Сохранить как", "", ";;".join(formats.keys())
        )

        if path:
            for fmt, get_content in formats.items():
                if fmt == selected_filter:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(get_content())
                    QMessageBox.information(
                        self, "Сохранено", f"Файл успешно сохранен как {path}"
                    )
                    break
