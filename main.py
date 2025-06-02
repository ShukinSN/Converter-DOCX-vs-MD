import os
import sys
from PyQt5.QtWidgets import QApplication
from src.gui.palette import DarkPalette
from src.gui.main_window import DocxToMarkdownConverter
from src.dependencies.checker import DependencyChecker


def main():
    try:
        if not DependencyChecker.check():
            return 1

        app = QApplication(sys.argv)
        DarkPalette.apply(app)

        converter = DocxToMarkdownConverter()
        converter.show()

        return sys.exit(app.exec_())
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        return 1


if __name__ == "__main__":
    main()
