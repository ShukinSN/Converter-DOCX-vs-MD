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

        # === Нормализация входных данных ===
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

        self._assign_appendix_letters()

    def _assign_appendix_letters(self):
        appendix_indices = [i for i, meta in enumerate(self.files_with_meta) if meta[2]]
        for pos, idx in enumerate(appendix_indices):
            if self.files_with_meta[idx][3].strip():
                continue
            letter_index = pos % len(self.RUSSIAN_LETTERS)
            letter = self.RUSSIAN_LETTERS[letter_index]
            if pos >= len(self.RUSSIAN_LETTERS):
                letter += str((pos // len(self.RUSSIAN_LETTERS)) + 1)
            self.files_with_meta[idx][3] = letter

    # ──────────────────────────────────────────────────────────────
    # НОВАЯ ФУНКЦИЯ: превращаем blockquotes → кодовые блоки
    # ──────────────────────────────────────────────────────────────
    def _convert_blockquotes_to_code(self, md_path: Path):
        """
        После конвертации Pandoc часто делает из отступов в Word цитаты (>).
        Мы превращаем их в настоящие кодовые блоки (4 пробела или ```).
        """
        try:
            content = md_path.read_text(encoding="utf-8")

            # Регулярное выражение ищет блоки цитат (включая вложенные)
            # Группа 1 — содержимое блока без ведущих >
            def replacer(match):
                block = match.group(0)
                lines = block.split("\n")
                code_lines = [
                    line.lstrip("> ").rstrip() for line in lines if line.strip()
                ]
                code_block = "\n".join("    " + line for line in code_lines)
                return code_block + "\n"

            # Заменяем все цитаты, идущие подряд (многострочные блоки)
            # Паттерн: строки, начинающиеся с > (может быть несколько пробелов после >)
            new_content = re.sub(
                r"^([ \t]*>(?:[ \t].*)?(?:\n|$))+",
                replacer,
                content,
                flags=re.MULTILINE,
            )

            # Иногда Pandoc оставляет пустые строки с > — чистим их
            new_content = re.sub(
                r"^[ \t]*>\s*$(\n|$)", "", new_content, flags=re.MULTILINE
            )

            # ─────────────────────── ДОПОЛНИТЕЛЬНО: Обрабатываем inline-команды в «кавычках» → `code` ───────────────────────
            # Заменяем «команда» на `команда`, если это выглядит как CLI-команда (содержит @, #, config, interface и т.д.)
            def inline_replacer(match):
                cmd = match.group(1).strip()
                # Проверка: если это команда (адаптируйте под ваши документы)
                if re.search(
                    r"[@#]|config|interface|vlan|ip|admin|administrator|Switch|exit|end|show|write|no",
                    cmd,
                    re.IGNORECASE,
                ):
                    return f"`{cmd}`"
                return match.group(0)  # Оставляем как есть, если не команда

            new_content = re.sub(r"«(.*?)»", inline_replacer, new_content)

            # ─────────────────────────────────────────────────────────────────────

            md_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            self.error_occurred.emit(f"Ошибка обработки цитат → код: {e}")

    # ──────────────────────────────────────────────────────────────

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

                output_root = Path(self.output_folder)
                output_root.mkdir(parents=True, exist_ok=True)

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

                safe_name = sanitize_filename(input_path.stem)
                output_path = output_dir / f"{safe_name}.md"

                if len(str(output_path)) > 240:
                    safe_name = safe_name[:100] + "..."
                    output_path = output_dir / f"{safe_name}.md"

                if output_path.exists() and not self.options.get("overwrite"):
                    success_count += 1
                    self.conversion_finished.emit(
                        filename,
                        f"Пропущено (уже существует): {safe_name}.md",
                        str(output_path),
                    )
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

                    # Убираем экранирование комментариев
                    try:
                        content = output_path.read_text(encoding="utf-8")
                        content = content.replace(r"\<!--", "<!--").replace(
                            r"--\>", "-->"
                        )
                        content = content.replace(r"\<", "<").replace(r"\>", ">")
                        output_path.write_text(content, encoding="utf-8")
                    except Exception as e:
                        self.error_occurred.emit(f"Ошибка снятия экранирования: {e}")

                    # ─────────────────────── ПОСТОБРАБОТКА ───────────────────────
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
                                if img.suffix.lower() == ".emf":
                                    png_path = convert_emf_to_png(img)
                                    if png_path:
                                        shutil.copy2(
                                            png_path, images_dir / png_path.name
                                        )
                                        rules[f"media/{img.name}"] = (
                                            f"images/{png_path.name}"
                                        )
                                else:
                                    shutil.copy2(img, images_dir / img.name)
                                    rules[f"media/{img.name}"] = f"images/{img.name}"
                    if rules:
                        replace_image_links(output_path, rules)

                    if self.options.get("toc"):
                        fix_links_and_toc(output_path)

                    # ─────────────────────── НОВАЯ ОБРАБОТКА ЦИТАТ → КОД ───────────────────────
                    self._convert_blockquotes_to_code(output_path)
                    # ─────────────────────────────────────────────────────────────────────

                    has_figures = "figure-container" in output_path.read_text(
                        encoding="utf-8"
                    )
                    has_tables = "table-caption" in output_path.read_text(
                        encoding="utf-8"
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
