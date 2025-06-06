import os
import re
import shutil
import tempfile
import zipfile
from PyQt5.QtCore import QThread, pyqtSignal
import pypandoc
from .utils import (
    sanitize_filename,
    convert_emf_to_png,
    process_images,
    fix_links_and_toc,
    replace_image_links,
)
from os.path import normpath, basename


class EnhancedConverterThread(QThread):
    progress_updated = pyqtSignal(int, str)
    conversion_finished = pyqtSignal(str, str, str)
    finished_all = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self, files, output_folder, options):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.options = options
        self._is_running = True
        self.processed_images = set()

    def run(self):  # Основной процесс конвертации с обработкой ошибок.
        total_files = len(self.files)
        success_count = 0

        for i, input_path in enumerate(self.files):
            if not self._is_running:
                break

            filename = os.path.basename(input_path)
            self.progress_updated.emit(int((i + 1) / total_files * 100), filename)

            try:
                if not os.access(input_path, os.R_OK):
                    raise PermissionError(f"Нет прав на чтение файла: {filename}")

                if not os.access(self.output_folder, os.W_OK):
                    raise PermissionError(
                        f"Нет прав на запись в папку: {self.output_folder}"
                    )

                if not os.path.exists(input_path):
                    raise FileNotFoundError(f"Файл не найден: {filename}")

                if not zipfile.is_zipfile(input_path):
                    raise ValueError(f"Неверный формат DOCX: {filename}")

                base_name = os.path.splitext(filename)[0]
                safe_name = sanitize_filename(base_name)
                output_path = os.path.join(self.output_folder, f"{safe_name}.md")

                if os.path.exists(output_path) and not self.options.get("overwrite"):
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

                    pypandoc.convert_file(
                        input_path,
                        "markdown",
                        outputfile=output_path,
                        format="docx",
                        extra_args=extra_args,
                    )

                    process_images(output_path, temp_dir)
                    replacement_rules = {}
                    for f in os.listdir(os.path.join(temp_dir, "media")):
                        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                            old_path = os.path.join("media", f)
                            new_path = os.path.join("images", f)
                            replacement_rules[old_path] = new_path
                    replace_image_links(output_path, replacement_rules)
                    if self.options.get("toc"):
                        fix_links_and_toc(output_path)

                success_count += 1
                self.conversion_finished.emit(
                    filename, f"Успешно: {safe_name}.md", output_path
                )

            except Exception as e:
                error_msg = f"Ошибка ({filename}): {str(e)}"
                self.error_occurred.emit(error_msg)
                self.conversion_finished.emit(filename, error_msg, "")

        self.finished_all.emit(success_count)

    def stop(self):  # Безопасная остановка потока.
        self._is_running = False
