# Copyright (c) 2025 [Schukin Sergey or CPA]
# Licensed under the MIT License. See LICENSE file in the project root for details.
import os
import sys
from PyQt5.QtWidgets import QApplication
from gui.palette import DarkPalette
from gui.main_window import DocxToMarkdownConverter
from dependencies.checker import DependencyChecker


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
