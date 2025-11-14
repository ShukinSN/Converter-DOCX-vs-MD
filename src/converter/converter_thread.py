import os
import re
import shutil
import tempfile
import zipfile
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
    """Поток для конвертации файлов."""

    progress_updated = pyqtSignal(int, str)
    conversion_finished = pyqtSignal(str, str, str)
    finished_all = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, options, project_root):
        """
        files: list[tuple[str, str|None]] — (full_path, base_folder_str_or_None)
               или list[str] — старый формат (обратная совместимость)
        """
        super().__init__()
        # === НОВОЕ: Поддержка нового формата ===
        if files and isinstance(files[0], tuple):
            self.files_with_bases = files  # [(path, base_folder), ...]
        else:
            self.files_with_bases = [
                (f, None) for f in files
            ]  # старый формат → base_folder=None
        # === КОНЕЦ НОВОГО ===

        self.output_folder = output_folder
        self.options = options
        self.project_root = Path(project_root)
        self._is_running = True
        self.successful_files = []  # Новое: список путей успешных MD-файлов
        self.chapter_groups = {}  # Добавляем для хранения групп

    def run(self):
        """Основной цикл конвертации."""
        total_files = len(self.files_with_bases)
        success_count = 0

        appendix_letter = self.options.get("appendix_letter", "А")
        is_appendix = self.options.get("appendix", False)

        for i, (input_path_str, base_folder_str) in enumerate(self.files_with_bases):
            if not self._is_running:
                break

            input_path = Path(input_path_str).resolve()
            base_folder = Path(base_folder_str) if base_folder_str else None
            filename = input_path.name

            self.progress_updated.emit(
                int((i / total_files) * 80), f"Обработка: {filename}"
            )

            try:
                if not input_path.exists():
                    raise FileNotFoundError(f"Файл не найден: {filename}")
                if not os.access(input_path, os.R_OK):
                    raise PermissionError(f"Нет прав на чтение: {filename}")

                output_root = Path(self.output_folder).resolve()
                output_root.mkdir(parents=True, exist_ok=True)

                # === НОВОЕ: Определение выходной папки с сохранением структуры ===
                if base_folder and input_path.parent != base_folder:
                    rel_dir = input_path.parent.relative_to(base_folder)
                    output_dir = output_root / rel_dir
                else:
                    output_dir = output_root
                output_dir.mkdir(parents=True, exist_ok=True)
                # === КОНЕЦ НОВОГО ===

                output_images_dir = output_dir / "images"
                output_images_dir.mkdir(exist_ok=True)

                if not zipfile.is_zipfile(input_path):
                    raise ValueError(f"Неверный формат DOCX: {filename}")

                base_name = input_path.stem
                safe_name = sanitize_filename(base_name)
                output_path = output_dir / f"{safe_name}.md"

                if output_path.exists() and not self.options.get("overwrite"):
                    raise FileExistsError(f"Файл уже существует: {output_path}")

                with tempfile.TemporaryDirectory() as temp_dir:
                    extra_args = [
                        f"--extract-media={temp_dir}",
                        "--wrap=none",
                        "--to=gfm",
                        "--standalone",
                        "--reference-links",
                    ]
                    if self.options.get("preserve_tabs"):
                        extra_args.append("--preserve-tabs")

                    try:
                        pypandoc.convert_file(
                            str(input_path),
                            "markdown",
                            outputfile=str(output_path),
                            format="docx",
                            extra_args=extra_args,
                        )
                    except Exception as e:
                        raise RuntimeError(f"Ошибка Pandoc: {str(e)}")

                    self.progress_updated.emit(
                        int((i / total_files) * 80 + 10), f"Конвертирован: {filename}"
                    )

                    # === СТАРЫЙ КОД: Обработка изображений и таблиц ===
                    try:
                        process_images(
                            output_path,
                            temp_dir,
                            self.project_root,
                            output_images_dir,
                            is_appendix=is_appendix,
                            appendix_letter=appendix_letter,
                        )
                        self.progress_updated.emit(
                            int((i / total_files) * 80 + 15),
                            f"Обработаны изображения: {filename}",
                        )
                    except Exception as e:
                        raise RuntimeError(f"Ошибка обработки изображений: {str(e)}")

                    try:
                        process_tables(
                            output_path,
                            self.project_root,
                            is_appendix=is_appendix,
                            appendix_letter=appendix_letter,
                        )
                        self.progress_updated.emit(
                            int((i / total_files) * 80 + 20),
                            f"Обработаны подписи таблиц: {filename}",
                        )
                    except Exception as e:
                        raise RuntimeError(f"Ошибка обработки таблиц: {str(e)}")

                    replacement_rules = {}
                    media_dir = Path(temp_dir) / "media"
                    if media_dir.exists():
                        for f in media_dir.iterdir():
                            if f.suffix.lower() in (
                                ".png",
                                ".jpg",
                                ".jpeg",
                                ".gif",
                                ".emf",
                            ):
                                old_path = f"media/{f.name}"
                                new_path = f"images/{f.name}"
                                dest_path = output_images_dir / f.name
                                if f.suffix.lower() == ".emf":
                                    png_path = convert_emf_to_png(f)
                                    if png_path:
                                        shutil.copy2(
                                            png_path, output_images_dir / png_path.name
                                        )
                                        new_path = f"images/{png_path.name}"
                                else:
                                    shutil.copy2(f, dest_path)
                                replacement_rules[old_path] = new_path

                    if replacement_rules:
                        try:
                            replace_image_links(output_path, replacement_rules)
                            self.progress_updated.emit(
                                int((i / total_files) * 80 + 25),
                                f"Заменены ссылки на изображения: {filename}",
                            )
                        except Exception as e:
                            raise RuntimeError(f"Ошибка замены ссылок: {str(e)}")

                    if self.options.get("toc"):
                        try:
                            fix_links_and_toc(output_path)
                            self.progress_updated.emit(
                                int((i / total_files) * 80 + 30),
                                f"Обработаны ссылки и оглавление: {filename}",
                            )
                        except Exception as e:
                            self.error_occurred.emit(
                                f"Ошибка обработки оглавления ({filename}): {str(e)}"
                            )

                    with open(output_path, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                    has_images = (
                        '<div class="figure-container">' in content
                        or '<div class="app-container">' in content
                    )
                    has_tables = (
                        '<div class="table-caption">' in content
                        or '<div class="app_table-caption">' in content
                    )

                    if has_images or has_tables:
                        try:
                            append_or_update_styles(
                                output_path,
                                self.project_root,
                                has_images,
                                has_tables,
                                is_appendix=is_appendix,
                                appendix_letter=appendix_letter,
                            )
                        except Exception as e:
                            self.error_occurred.emit(
                                f"Ошибка при добавлении стилей ({filename}): {str(e)}"
                            )
                    # === КОНЕЦ СТАРОГО КОДА ===

                    success_count += 1
                    self.conversion_finished.emit(
                        filename, f"Успешно: {safe_name}.md", str(output_path)
                    )
                    self.successful_files.append(str(output_path))

            except Exception as e:
                error_msg = f"Ошибка ({filename}): {str(e)}"
                self.error_occurred.emit(error_msg)
                self.conversion_finished.emit(filename, error_msg, "")

        self.finished_all.emit(success_count)

    def stop(self):
        self._is_running = False
