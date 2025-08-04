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
    progress_updated = pyqtSignal(int, str)
    conversion_finished = pyqtSignal(str, str, str)
    finished_all = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, options, project_root):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.options = options
        self.project_root = Path(project_root)
        self._is_running = True

    def run(self):
        total_files = len(self.files)
        success_count = 0

        for i, input_path in enumerate(self.files):
            if not self._is_running:
                break

            filename = Path(input_path).name
            self.progress_updated.emit(
                int((i / total_files) * 80), f"Обработка файла: {filename}"
            )

            try:
                # Получаем абсолютный путь и проверяем файл
                input_path = Path(input_path).resolve()
                if not input_path.exists():
                    raise FileNotFoundError(f"Файл не найден: {filename}")
                if not os.access(input_path, os.R_OK):
                    raise PermissionError(f"Нет прав на чтение файла: {filename}")

                # Проверяем папку для сохранения
                output_folder = Path(self.output_folder).resolve()
                if not output_folder.exists():
                    output_folder.mkdir(parents=True)
                if not os.access(output_folder, os.W_OK):
                    raise PermissionError(
                        f"Нет прав на запись в папку: {self.output_folder}"
                    )

                # Проверяем что файл является валидным DOCX
                if not zipfile.is_zipfile(input_path):
                    raise ValueError(f"Неверный формат DOCX: {filename}")

                base_name = input_path.stem
                safe_name = sanitize_filename(base_name)
                output_path = output_folder / f"{safe_name}.md"

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

                    # Конвертация с обработкой путей
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
                        int((i / total_files) * 80 + 10),
                        f"Конвертирован в Markdown: {filename}",
                    )

                    # Обработка изображений
                    try:
                        process_images(output_path, temp_dir, self.project_root)
                        self.progress_updated.emit(
                            int((i / total_files) * 80 + 15),
                            f"Обработаны изображения: {filename}",
                        )
                    except Exception as e:
                        raise RuntimeError(f"Ошибка обработки изображений: {str(e)}")

                    # Обработка таблиц
                    try:
                        process_tables(output_path, self.project_root)
                        self.progress_updated.emit(
                            int((i / total_files) * 80 + 20),
                            f"Обработаны подписи таблиц: {filename}",
                        )
                    except Exception as e:
                        raise RuntimeError(f"Ошибка обработки таблиц: {str(e)}")

                    # Замена ссылок на изображения
                    replacement_rules = {}
                    media_dir = Path(temp_dir) / "media"
                    if media_dir.exists():
                        for f in media_dir.iterdir():
                            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
                                old_path = f"media/{f.name}"
                                new_path = f"images/{f.name}"
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

                    # Оглавление
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

                    # Добавление стилей
                    with open(output_path, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                    has_images = '<div class="figure-container">' in content
                    has_tables = '<div class="table-caption">' in content

                    if has_images or has_tables:
                        try:
                            append_or_update_styles(
                                output_path, self.project_root, has_images, has_tables
                            )
                        except Exception as e:
                            self.error_occurred.emit(
                                f"Ошибка при добавлении стилей ({filename}): {str(e)}"
                            )

                    success_count += 1
                    self.conversion_finished.emit(
                        filename, f"Успешно: {safe_name}.md", str(output_path)
                    )

            except Exception as e:
                error_msg = f"Ошибка ({filename}): {str(e)}"
                self.error_occurred.emit(error_msg)
                self.conversion_finished.emit(filename, error_msg, "")

        self.finished_all.emit(success_count)

    def stop(self):
        self._is_running = False
