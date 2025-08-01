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
from pathlib import Path
import markdown


class ModernPreviewWindow(QMainWindow):
    _cached_styles = None  # Кэш для CSS стилей

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр Markdown")
        self.setGeometry(200, 200, 800, 600)
        self.project_root = Path(__file__).resolve().parents[2]
        self.init_ui()
        print("Инициализировано окно предпросмотра")

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
        print("Созданы вкладки предпросмотра")

        self.close_button = QPushButton("Закрыть")
        self.close_button.clicked.connect(self.close)

        layout.addWidget(self.tab_widget)
        layout.addWidget(self.close_button)
        print("Интерфейс окна предпросмотра настроен")

    @classmethod
    def get_styles(cls, project_root):
        if cls._cached_styles is None:
            styles = []
            css_files = [
                project_root / "src" / "css" / "styles_images.css",
                project_root / "src" / "css" / "styles_tables.css",
                project_root / "src" / "css" / "styles_appendices.css",
            ]

            for css_path in css_files:
                try:
                    if css_path.exists():
                        with open(css_path, "r", encoding="utf-8") as css_file:
                            styles.append(css_file.read().strip())
                        print(f"Загружен CSS из {css_path}")
                    else:
                        print(f"Файл CSS не найден: {css_path}")
                except Exception as e:
                    print(f"Ошибка при загрузке CSS из {css_path}: {str(e)}")

            cls._cached_styles = "\n".join(styles) if styles else ""
            print("CSS стили закэшированы")

        return cls._cached_styles

    def set_content(self, content):
        try:
            self.markdown_view.setPlainText(content)
            print("Markdown контент установлен")

            html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
            print("Конвертация Markdown в HTML выполнена")

            combined_styles = self.get_styles(self.project_root)
            html = f"<style>\n{combined_styles}\n</style>\n{html}"

            self.html_view.setHtml(html)
            print("HTML контент отображен")

        except Exception as e:
            error_msg = f"Ошибка конвертации в HTML: {str(e)}"
            print(error_msg)
            self.html_view.setPlainText(error_msg)

    def closeEvent(self, event):
        if self.parent():
            self.parent().preview_window = None
            print("Ссылка на окно предпросмотра удалена")
        event.accept()
        print("Окно предпросмотра закрыто")
