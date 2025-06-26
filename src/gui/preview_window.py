from PyQt5.QtWidgets import (
    QMainWindow,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QTabWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import markdown


class ModernPreviewWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр Markdown")
        self.setGeometry(200, 200, 800, 600)
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        self.markdown_view = QTextEdit()
        self.markdown_view.setReadOnly(True)
        self.markdown_view.setFont(QFont("Consolas", 10))
        self.html_view = QTextEdit()
        self.html_view.setReadOnly(True)
        self.html_view.setFont(QFont("Consolas", 10))

        self.tab_widget.addTab(self.markdown_view, "Markdown")
        self.tab_widget.addTab(self.html_view, "HTML")

        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.close)

        layout.addWidget(self.tab_widget)
        layout.addWidget(self.close_button)

    def set_content(self, content):
        self.markdown_view.setPlainText(content)
        try:
            html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
            # Добавление CSS для поддержки нумерации рисунков
            css = """<style>
/* initialise the counter */
body { counter-reset: figureCounter; }
/* increment the counter for every instance of a figure */
figure { counter-increment: figureCounter; }
/* prepend the counter to the figcaption content */
figure figcaption:before {
    content: "Рисунок " counter(figureCounter) " - ";
}
figure figcaption {
    text-align: center;
    margin-top: 8px;
}
</style>
"""
            html = css + "\n" + html
            self.html_view.setHtml(html)
        except Exception as e:
            self.html_view.setPlainText(f"Ошибка конвертации в HTML: {str(e)}")

    def closeEvent(self, event):
        if self.parent():
            self.parent().preview_window = None
        event.accept()
