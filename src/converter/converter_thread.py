# converter/converter_thread.py
import os
import re
import shutil
import tempfile
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
import pypandoc
from .utils import (
    sanitize_filename,
    convert_emf_to_png,
    process_images,
    process_tables,
    fix_links_and_toc,
    replace_image_links,
    append_or_update_styles,
)


class EnhancedConverterThread(QThread):
    progress_updated = pyqtSignal(int, str)
    conversion_finished = pyqtSignal(str, str, str)  # filename, message, output_path
    finished_all = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    RUSSIAN_LETTERS = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"

    def __init__(self, files, output_folder, options, project_root):
        super().__init__()
        self.output_folder = output_folder
        self.options = options
        self.project_root = Path(project_root)
        self._is_running = True
        self.successful_files = []

        # === Нормализация входных данных: поддержка (path, base_folder, is_appendix, letter) ===
        self.files_with_meta = []
        for item in files:
            if isinstance(item, str):
                self.files_with_meta.append([item, None, False, ""])
            elif len(item) == 2:
                path, base = item
                self.files_with_meta.append([path, base, False, ""])
            elif len(item) == 4:
                self.files_with_meta.append(list(item))
            else:
                raise ValueError(f"Неподдерживаемый формат элемента: {item}")

        # Автоматическое назначение букв для приложений
        self._assign_appendix_letters()

    def _assign_appendix_letters(self):
        """Безопасно назначает буквы приложениям, если они не заданы вручную."""
        appendix_indices = [i for i, meta in enumerate(self.files_with_meta) if meta[2]]

        for pos, idx in enumerate(appendix_indices):
            if self.files_with_meta[idx][3].strip():
                continue  # буква уже указана вручную

            letter_index = pos % len(self.RUSSIAN_LETTERS)
            letter = self.RUSSIAN_LETTERS[letter_index]

            if pos >= len(self.RUSSIAN_LETTERS):
                letter += str((pos // len(self.RUSSIAN_LETTERS)) + 1)

            self.files_with_meta[idx][3] = letter

    def run(self):
        total = len(self.files_with_meta)
        success_count = 0

        for i, (
            input_path_str,
            base_folder_str,
            is_appendix,
            appendix_letter,
        ) in enumerate(self.files_with_meta):
            if not self._is_running:
                break

            input_path = Path(input_path_str).resolve()
            filename = input_path.name

            self.progress_updated.emit(int(i / total * 80), f"Обработка: {filename}")

            try:
                if not input_path.exists():
                    raise FileNotFoundError(f"Файл не найден: {input_path}")

                # === Выходная папка ===
                output_root = Path(self.output_folder)
                output_root.mkdir(parents=True, exist_ok=True)

                # Определяем относительную структуру папок
                rel_dir = Path()
                if base_folder_str:
                    try:
                        rel_dir = input_path.parent.relative_to(Path(base_folder_str))
                    except ValueError:
                        pass  # если не в базовой папке — просто в корень

                output_dir = output_root / rel_dir
                output_dir.mkdir(parents=True, exist_ok=True)
                images_dir = output_dir / "images"
                images_dir.mkdir(exist_ok=True)

                # Имя файла — без префикса [А], [Б] и т.п.
                safe_name = sanitize_filename(input_path.stem)
                output_path = output_dir / f"{safe_name}.md"

                # Защита от слишком длинных путей (Windows)
                if len(str(output_path)) > 240:
                    safe_name = safe_name[:100] + "..."
                    output_path = output_dir / f"{safe_name}.md"

                # Пропуск, если файл существует и перезапись отключена
                if output_path.exists() and not self.options.get("overwrite"):
                    success_count += 1
                    self.conversion_finished.emit(
                        filename,
                        f"Пропущено (уже существует): {safe_name}.md",
                        str(output_path),
                    )
                    self.progress_updated.emit(int((i + 1) / total * 100), filename)
                    continue

                with tempfile.TemporaryDirectory() as tmp_dir:
                    # === Конвертация через pandoc ===
                    extra_args = [
                        f"--extract-media={tmp_dir}",
                        "--wrap=none",
                        "--to=gfm",
                        "--standalone",
                        "--reference-links",
                    ]
                    if self.options.get("preserve_tabs"):
                        extra_args.append("--preserve-tabs")

                    pypandoc.convert_file(
                        str(input_path),
                        "markdown",
                        outputfile=str(output_path),
                        format="docx",
                        extra_args=extra_args,
                    )

                    # === УДАЛЕНИЕ ЭКРАНИРОВАНИЯ HTML-КОММЕНТАРИЕВ ===
                    try:
                        with open(output_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Основные замены: \<!-- → <!-- и --\> → -->
                        content = content.replace(r"\<!--", "<!--")
                        content = content.replace(r"--\>", "-->")

                        # Дополнительно — на случай, если pandoc экранирует < и > отдельно
                        content = content.replace(r"\<", "<").replace(r"\>", ">")

                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write(content)
                    except Exception as e:
                        self.error_occurred.emit(f"Ошибка снятия экранирования: {e}")

                    # === ПОСТОБРАБОТКА: изображения, таблицы, ссылки, стили ===
                    try:
                        # Обработка изображений и таблиц
                        process_images(
                            output_path,
                            tmp_dir,
                            self.project_root,
                            images_dir,
                            is_appendix=is_appendix,
                            appendix_letter=appendix_letter,
                        )
                        process_tables(
                            output_path,
                            self.project_root,
                            is_appendix=is_appendix,
                            appendix_letter=appendix_letter,
                        )

                        # Замена ссылок на изображения из media → images
                        rules = {}
                        media_dir = Path(tmp_dir) / "media"
                        if media_dir.exists():
                            for img in media_dir.iterdir():
                                if img.suffix.lower() in {
                                    ".png",
                                    ".jpg",
                                    ".jpeg",
                                    ".gif",
                                    ".emf",
                                }:
                                    old = f"media/{img.name}"
                                    if img.suffix.lower() == ".emf":
                                        png_path = convert_emf_to_png(img)
                                        if png_path:
                                            shutil.copy2(
                                                png_path, images_dir / png_path.name
                                            )
                                            rules[old] = f"images/{png_path.name}"
                                    else:
                                        shutil.copy2(img, images_dir / img.name)
                                        rules[old] = f"images/{img.name}"
                        if rules:
                            replace_image_links(output_path, rules)

                        # Оглавление
                        if self.options.get("toc"):
                            fix_links_and_toc(output_path)

                        # Добавление стилей
                        content = output_path.read_text(encoding="utf-8-sig")
                        has_figures = any(
                            tag in content
                            for tag in ["figure-container", "app-container"]
                        )
                        has_tables = any(
                            tag in content
                            for tag in ["table-caption", "app_table-caption"]
                        )
                        if has_figures or has_tables:
                            append_or_update_styles(
                                output_path,
                                self.project_root,
                                has_figures,
                                has_tables,
                                is_appendix=is_appendix,
                                appendix_letter=appendix_letter,
                            )

                    except Exception as e:
                        self.error_occurred.emit(
                            f"Ошибка постобработки ({filename}): {e}"
                        )

                    success_count += 1
                    self.conversion_finished.emit(
                        filename,
                        f"Успешно конвертирован: {safe_name}.md",
                        str(output_path),
                    )
                    self.successful_files.append(str(output_path))

            except Exception as e:
                msg = f"Ошибка при обработке {filename}: {str(e)}"
                self.error_occurred.emit(msg)
                self.conversion_finished.emit(filename, msg, None)

            finally:
                self.progress_updated.emit(int((i + 1) / total * 100), filename)

        self.finished_all.emit(success_count)

    def stop(self):
        self._is_running = False
