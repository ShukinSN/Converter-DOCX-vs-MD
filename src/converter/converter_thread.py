import os
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

    RUSSIAN_LETTERS = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ"

    def __init__(self, files, output_folder, options, project_root):
        super().__init__()
        self.output_folder = output_folder
        self.options = options
        self.project_root = Path(project_root)
        self._is_running = True
        self.successful_files = []
        self.chapter_groups = {}

        # === БЕЗОПАСНАЯ НОРМАЛИЗАЦИЯ ===
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
                raise ValueError(f"Неподдерживаемый формат: {item}")

        # Автоматическое назначение букв (теперь безопасно!)
        self._assign_appendix_letters()

    def _assign_appendix_letters(self):
        """Безопасно назначает буквы приложениям."""
        appendix_indices = [
            i
            for i, meta in enumerate(self.files_with_meta)
            if meta[2]  # is_appendix == True
        ]

        for pos, idx in enumerate(appendix_indices):
            if self.files_with_meta[idx][3].strip():
                continue  # уже есть буква

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
                    raise FileNotFoundError("Файл не найден")

                output_root = Path(self.output_folder)
                output_root.mkdir(parents=True, exist_ok=True)

                # Структура папок
                rel_dir = Path()
                if base_folder_str:
                    try:
                        rel_dir = input_path.parent.relative_to(Path(base_folder_str))
                    except ValueError:
                        pass
                output_dir = output_root / rel_dir
                output_dir.mkdir(parents=True, exist_ok=True)

                images_dir = output_dir / "images"
                images_dir.mkdir(exist_ok=True)

                # ИМЯ ФАЙЛА — БЕЗ ПРЕФИКСА [А]!
                safe_name = sanitize_filename(input_path.stem)
                output_path = output_dir / f"{safe_name}.md"

                # Защита от слишком длинных путей (Windows)
                if len(str(output_path)) > 240:
                    safe_name = safe_name[:100] + "..."
                    output_path = output_dir / f"{safe_name}.md"

                if output_path.exists() and not self.options.get("overwrite"):
                    success_count += 1
                    self.conversion_finished.emit(
                        filename, f"Пропущено: {safe_name}.md", str(output_path)
                    )
                    self.progress_updated.emit(int((i + 1) / total * 100), filename)
                    continue

                with tempfile.TemporaryDirectory() as tmp_dir:
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

                    # === Все обработки (изображения, таблицы, стили и т.д.) ===
                    try:
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

                        # Замена ссылок на изображения
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
                                        png = convert_emf_to_png(img)
                                        if png:
                                            shutil.copy2(png, images_dir / png.name)
                                            rules[old] = f"images/{png.name}"
                                    else:
                                        shutil.copy2(img, images_dir / img.name)
                                        rules[old] = f"images/{img.name}"
                        if rules:
                            replace_image_links(output_path, rules)

                        if self.options.get("toc"):
                            fix_links_and_toc(output_path)

                        # Стили
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
                            f"Постобработка ошибка ({filename}): {e}"
                        )

                    success_count += 1
                    self.conversion_finished.emit(
                        filename, f"Успешно: {safe_name}.md", str(output_path)
                    )
                    self.successful_files.append(str(output_path))

            except Exception as e:
                msg = f"Ошибка конвертации {filename}: {str(e)}"
                self.error_occurred.emit(msg)
                self.conversion_finished.emit(filename, msg, None)

            finally:
                self.progress_updated.emit(int((i + 1) / total * 100), filename)

        self.finished_all.emit(success_count)

    def stop(self):
        self._is_running = False
