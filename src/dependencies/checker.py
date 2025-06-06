from PyQt5.QtWidgets import QMessageBox
import pypandoc


class DependencyChecker:
    @staticmethod
    def check():
        missing = []
        try:
            version = pypandoc.get_pandoc_version()
            if tuple(map(int, version.split("."))) < (2, 14):
                missing.append(
                    f"Pandoc (версия {version} найдена, требуется 2.14 или выше)"
                )
        except (ImportError, OSError):
            missing.append("Pandoc (установите с https://pandoc.org/installing.html)")

        for lib in ["markdown", "bs4", "PyQt5", "wand"]:
            try:
                __import__(lib)
            except ImportError:
                missing.append(f"{lib} (pip install {lib})")

        if missing:
            msg = "Не хватает зависимостей:\n" + "\n".join(missing)
            QMessageBox.critical(None, "Ошибка зависимостей", msg)
            return False
        return True
