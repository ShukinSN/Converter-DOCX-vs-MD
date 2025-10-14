from PyQt5.QtWidgets import QMainWindow, QTextEdit, QSplitter, QWidget, QVBoxLayout
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt
from pathlib import Path
import sys
import markdown


class ModernPreviewWindow(QMainWindow):
    """Окно предпросмотра Markdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр Markdown")
        self.setGeometry(200, 200, 800, 600)
        self.project_root = Path(__file__).resolve().parents[2]
        print(f"Project root: {self.project_root}")
        self.init_ui()
        print("Инициализировано окно предпросмотра")

    def init_ui(self):
        """Инициализация UI окна предпросмотра."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)
        self.markdown_view = QTextEdit()
        self.markdown_view.setReadOnly(True)
        self.html_view = QWebEngineView()
        splitter.addWidget(self.markdown_view)
        splitter.addWidget(self.html_view)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)

    @classmethod
    def get_styles(cls, project_root, is_appendix=False, appendix_letter="А"):
        """Получение стилей CSS для предпросмотра."""
        styles = []
        css_files = []
        base_path = Path(getattr(sys, "_MEIPASS", project_root))
        print(f"Base path for CSS: {base_path}")

        if is_appendix:
            css_files.append(base_path / "src" / "css" / "styles_appendices.css")
        else:
            css_files.extend(
                [
                    base_path / "src" / "css" / "styles_images.css",
                    base_path / "src" / "css" / "styles_tables.css",
                ]
            )

        for css_path in css_files:
            print(f"Checking CSS: {css_path}, exists: {css_path.exists()}")
            try:
                if css_path.exists():
                    with open(css_path, "r", encoding="utf-8") as css_file:
                        css_content = css_file.read().strip()
                        if is_appendix:
                            css_content = css_content.replace(
                                "var(--appLetter)", f'"{appendix_letter}"'
                            )
                        styles.append(css_content)
                    print(f"Loaded CSS from {css_path}")
                else:
                    print(f"CSS file not found: {css_path}")
            except Exception as e:
                print(f"Error loading CSS from {css_path}: {str(e)}")

        return "\n".join(styles) if styles else ""

    def set_content(self, content, is_appendix=False, appendix_letter="А"):
        """Установка содержимого для предпросмотра."""
        try:
            self.markdown_view.setPlainText(content)
            print("Markdown контент установлен")

            html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
            print("Конвертация Markdown в HTML выполнена")

            combined_styles = self.get_styles(
                self.project_root, is_appendix, appendix_letter
            )
            print(f"Combined styles: {combined_styles[:100]}...")
            html = f"<style>\n{combined_styles}\n</style>\n{html}"

            self.html_view.setHtml(html)
            print("HTML контент отображен")
        except Exception as e:
            error_msg = f"Ошибка конвертации в HTML: {str(e)}"
            print(error_msg)
            self.html_view.setPlainText(error_msg)

    def closeEvent(self, event):
        """Обработка закрытия окна."""
        if self.parent():
            self.parent().preview_window = None
            print("Ссылка на окно предпросмотра удалена")
        event.accept()
        print("Окно предпросмотра закрыто")
