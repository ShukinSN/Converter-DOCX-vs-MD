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
    process_tables,
    fix_links_and_toc,
    replace_image_links,
)
from os.path import normpath, basename


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
        self.project_root = project_root
        self._is_running = True
        self.processed_images = set()

    def run(self):
        total_files = len(self.files)
        success_count = 0

        for i, input_path in enumerate(self.files):
            if not self._is_running:
                break

            filename = os.path.basename(input_path)
            self.progress_updated.emit(
                int((i / total_files) * 80), f"Обработка файла: {filename}"
            )

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

                    self.progress_updated.emit(
                        int((i / total_files) * 80 + 10),
                        f"Конвертирован в Markdown: {filename}",
                    )

                    process_images(output_path, temp_dir, self.project_root)
                    self.progress_updated.emit(
                        int((i / total_files) * 80 + 15),
                        f"Обработаны изображения: {filename}",
                    )

                    process_tables(output_path, self.project_root)
                    self.progress_updated.emit(
                        int((i / total_files) * 80 + 20),
                        f"Обработаны подписи таблиц: {filename}",
                    )

                    replacement_rules = {}
                    media_dir = os.path.join(temp_dir, "media")
                    if os.path.exists(media_dir):
                        for f in os.listdir(media_dir):
                            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                                old_path = os.path.join("media", f)
                                new_path = os.path.join("images", f)
                                replacement_rules[old_path] = new_path
                    if replacement_rules:
                        replace_image_links(output_path, replacement_rules)
                        self.progress_updated.emit(
                            int((i / total_files) * 80 + 25),
                            f"Заменены ссылки на изображения: {filename}",
                        )

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

                    # Проверяем наличие элементов после обработки
                    with open(output_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    has_images = '<div class="figure-container">' in content
                    has_tables = '<div class="table-caption">' in content
                    print(
                        f"Для {filename}: has_images={has_images}, has_tables={has_tables}"
                    )

                    # Добавляем стили в конец файла с объединением и обработкой ошибок
                    style_marker = "<!-- DOCX2MD STYLES -->"
                    if has_images or has_tables:
                        try:
                            with open(output_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            if style_marker not in content:
                                styles = ""
                                with open(output_path, "a", encoding="utf-8") as f:
                                    f.write(f"\n\n{style_marker}\n<style>\n")
                                    if has_images:
                                        css_images_path = os.path.join(
                                            self.project_root,
                                            "src",
                                            "css",
                                            "styles_images.css",
                                        )
                                        print(
                                            f"Проверяю путь к styles_images.css: {css_images_path}"
                                        )
                                        if os.path.exists(css_images_path):
                                            with open(
                                                css_images_path, "r", encoding="utf-8"
                                            ) as css_file:
                                                styles += css_file.read()
                                                print(
                                                    f"Добавлены стили из {css_images_path}"
                                                )
                                        else:
                                            print(f"Файл {css_images_path} не найден")
                                    if has_tables:
                                        css_tables_path = os.path.join(
                                            self.project_root,
                                            "src",
                                            "css",
                                            "styles_tables.css",
                                        )
                                        print(
                                            f"Проверяю путь к styles_tables.css: {css_tables_path}"
                                        )
                                        if os.path.exists(css_tables_path):
                                            with open(
                                                css_tables_path, "r", encoding="utf-8"
                                            ) as css_file:
                                                styles += css_file.read()
                                                print(
                                                    f"Добавлены стили из {css_tables_path}"
                                                )
                                        else:
                                            print(f"Файл {css_tables_path} не найден")
                                    # Убедимся, что styles не пустой перед записью
                                    if styles:
                                        f.write(styles.strip() + "\n")
                                    f.write("</style>\n")
                                    print(f"Записан полный тег <style> для {filename}")
                            else:
                                # Обновляем существующий <style>, если он есть
                                updated_content = content
                                if has_images:
                                    css_images_path = os.path.join(
                                        self.project_root,
                                        "src",
                                        "css",
                                        "styles_images.css",
                                    )
                                    if os.path.exists(css_images_path):
                                        with open(
                                            css_images_path, "r", encoding="utf-8"
                                        ) as css_file:
                                            css_content = css_file.read().strip()
                                            if ".figure-container" not in content:
                                                updated_content = re.sub(
                                                    r"(<!-- DOCX2MD STYLES -->\n<style>)(.*?)(</style>)",
                                                    r"\1\2\n" + css_content + "\n\3",
                                                    updated_content,
                                                    flags=re.DOTALL,
                                                )
                                if has_tables:
                                    css_tables_path = os.path.join(
                                        self.project_root,
                                        "src",
                                        "css",
                                        "styles_tables.css",
                                    )
                                    if os.path.exists(css_tables_path):
                                        with open(
                                            css_tables_path, "r", encoding="utf-8"
                                        ) as css_file:
                                            css_content = css_file.read().strip()
                                            if ".table-caption" not in content:
                                                updated_content = re.sub(
                                                    r"(<!-- DOCX2MD STYLES -->\n<style>)(.*?)(</style>)",
                                                    r"\1\2\n" + css_content + "\n\3",
                                                    updated_content,
                                                    flags=re.DOTALL,
                                                )
                                if updated_content != content:
                                    with open(output_path, "w", encoding="utf-8") as f:
                                        f.write(updated_content)
                                        print(f"Обновлён тег <style> для {filename}")
                        except Exception as e:
                            print(
                                f"Ошибка при добавлении стилей для {filename}: {str(e)}"
                            )
                            self.error_occurred.emit(
                                f"Ошибка при добавлении стилей ({filename}): {str(e)}"
                            )

                    success_count += 1
                    self.conversion_finished.emit(
                        filename, f"Успешно: {safe_name}.md", output_path
                    )

            except Exception as e:
                error_msg = f"Ошибка ({filename}): {str(e)}"
                self.error_occurred.emit(error_msg)
                self.conversion_finished.emit(filename, error_msg, "")

        self.finished_all.emit(success_count)

    def stop(self):
        self._is_running = False
