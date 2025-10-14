import re
import os
import sys
import shutil
from pathlib import Path
from wand.image import Image
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning, module="wand.*")


def sanitize_filename(name):
    """Очистка имени файла от недопустимых символов."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def convert_emf_to_png(emf_path):
    """Конвертация EMF в PNG."""
    try:
        png_path = Path(emf_path).with_suffix(".png")
        with Image(filename=str(emf_path)) as img:
            img.format = "png"
            img.save(filename=str(png_path))
        return png_path
    except Exception as e:
        print(f"Ошибка конвертации {emf_path} в PNG: {str(e)}")
        return None


def process_images(
    md_path,
    temp_dir,
    project_root,
    output_images_dir,
    is_appendix=False,
    appendix_letter="А",
):
    md_path = Path(md_path)
    md_dir = md_path.parent
    images_folder = Path(output_images_dir)
    images_folder.mkdir(exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    figure_counter = 1
    lines = content.split("\n")
    new_lines = []
    i = 0
    in_table = False
    has_images = False

    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        if not in_table and stripped_line.startswith("|") and "|" in stripped_line[1:]:
            in_table = True
        elif in_table and not stripped_line.startswith("|"):
            in_table = False

        def process_image_match(match, is_markdown=True):
            nonlocal line, has_images, figure_counter
            src = match.group(2 if is_markdown else 1)
            if src.startswith("data:") or not src.strip():
                return None

            has_images = True
            original_name = Path(src.split("?")[0]).name
            name, ext = Path(original_name).stem, Path(original_name).suffix
            img_name = f"{name}_{timestamp}_{figure_counter}{ext.lower()}"
            img_name = sanitize_filename(img_name)

            possible_paths = [
                Path(temp_dir) / "media" / original_name,
                Path(temp_dir) / original_name,
                md_dir / original_name,
            ]
            src_path = next((p for p in possible_paths if p.exists()), None)

            if not src_path:
                print(f"Изображение не найдено: {original_name}")
                return None

            if src_path.suffix.lower() == ".emf":
                png_path = convert_emf_to_png(src_path)
                if png_path:
                    src_path = png_path
                    img_name = f"{name}_{timestamp}_{figure_counter}.png"
                    ext = ".png"

            file_counter = 1
            while (images_folder / img_name).exists():
                base_name = Path(img_name).stem
                if "_" in base_name:
                    base_name = base_name.rsplit("_", 1)[0]
                img_name = f"{base_name}_{file_counter}{ext}"
                file_counter += 1

            dest_path = images_folder / img_name
            shutil.copy2(src_path, dest_path)
            rel_path = dest_path.relative_to(md_dir).as_posix()

            if is_markdown:
                line = line.replace(src, rel_path)
            else:
                line = re.sub(
                    r'src="' + re.escape(src) + r'"', f'src="{rel_path}"', line
                )

            return rel_path

        # Пропускаем строки с подписями к рисункам
        if not in_table:
            if is_appendix and re.match(
                r"^(?:Рисунок|Рис\.?)\s*(?:[А-Яа-я]\.\d+|[А-Яа-я]\.|\.)\s*[-–—]\s*(.*)$",
                stripped_line,
                re.IGNORECASE,
            ):
                i += 1
                continue
            elif not is_appendix and re.match(
                r"^(?:Рисунок|Рис\.?)\s*\d+\s*[-–—]\s*(.*)$",
                stripped_line,
                re.IGNORECASE,
            ):
                i += 1
                continue

            img_match = None
            is_markdown = False

            for pattern, md in [
                (r"!\[([^\]]*)\]\(([^)]+)\)", True),
                (r'<img\s+[^>]*src="([^"]+)"[^>]*>', False),
            ]:
                match = re.match(pattern, stripped_line)
                if match:
                    img_match = match
                    is_markdown = md
                    break

            if img_match:
                src = img_match.group(2 if is_markdown else 1)
                if not src.startswith("data:") and src.strip():
                    rel_path = process_image_match(img_match, is_markdown)
                    if rel_path:
                        caption = "Изображение"
                        for j in range(1, 6):
                            if i + j >= len(lines):
                                break
                            next_line = lines[i + j].strip()
                            if is_appendix:
                                caption_match = re.match(
                                    r"^(?:Рисунок|Рис\.?)\s*(?:[А-Яа-я]\.\d+|[А-Яа-я]\.|\.)\s*[-–—]\s*(.*)$",
                                    next_line,
                                    re.IGNORECASE,
                                )
                            else:
                                caption_match = re.match(
                                    r"^(?:Рисунок|Рис\.?)\s*\d+\s*[-–—]\s*(.*)$",
                                    next_line,
                                    re.IGNORECASE,
                                )
                            if caption_match:
                                caption = caption_match.group(1).strip()
                                lines[i + j] = ""
                                break

                        container_class = (
                            "app-container" if is_appendix else "figure-container"
                        )
                        caption_class = (
                            "app-caption" if is_appendix else "figure-caption"
                        )

                        if is_markdown:
                            line = f'<div class="{container_class}">\n<img src="{rel_path}" alt="{img_match.group(1)}">\n<span class="{caption_class}">{caption}</span>\n</div>'
                        else:
                            updated_img = re.sub(
                                r'\s*alt="[^"]*"', "", img_match.group(0)
                            )
                            updated_img = updated_img.replace(src, rel_path)
                            line = f'<div class="{container_class}">\n{updated_img}\n<span class="{caption_class}">{caption}</span>\n</div>'
                        new_lines.append(line)
                        figure_counter += 1
                        i += 1
                        continue

        md_images = list(re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", line))
        for match in md_images:
            process_image_match(match, is_markdown=True)

        html_images = list(re.finditer(r'<img\s+[^>]*src="([^"]+)"[^>]*>', line))
        for match in html_images:
            process_image_match(match, is_markdown=False)

        new_lines.append(line)
        i += 1

    content = "\n".join(new_lines)

    if has_images:
        try:
            append_or_update_styles(
                md_path,
                project_root,
                has_images=True,
                has_tables=False,
                is_appendix=is_appendix,
                appendix_letter=appendix_letter,
            )
            print(f"Обработаны стили изображений для {md_path.name}")
        except Exception as e:
            print(
                f"Ошибка при добавлении стилей изображений для {md_path.name}: {str(e)}"
            )

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def process_tables(md_path, project_root, is_appendix=False, appendix_letter="А"):
    md_path = Path(md_path)
    has_tables = False

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    new_lines = []
    i = 0
    in_table = False

    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        if not in_table and stripped_line.startswith("|") and "|" in stripped_line[1:]:
            in_table = True
            has_tables = True
        elif in_table and not stripped_line.startswith("|"):
            in_table = False

        if not in_table:
            if is_appendix:
                caption_pattern = (
                    r"^(?:Таблица|Табл\.?)\s*([А-Яа-я]?)\.?(\d+)?\s*[-–—]\s*(.*)$"
                )
            else:
                caption_pattern = r"^(?:Таблица|Табл\.?)\s*(\d+)?\s*[-–—]\s*(.*)$"

            caption_match = re.match(caption_pattern, stripped_line, re.IGNORECASE)
            if caption_match:
                caption = (
                    caption_match.group(3).strip()
                    if is_appendix
                    else caption_match.group(2).strip()
                )
                caption_class = "app_table-caption" if is_appendix else "table-caption"
                new_lines.append(f'<div class="{caption_class}">{caption}</div>')
                has_tables = True
                i += 1
                continue

        new_lines.append(line)
        i += 1

    content = "\n".join(new_lines)

    if has_tables:
        try:
            append_or_update_styles(
                md_path,
                project_root,
                has_images=False,
                has_tables=True,
                is_appendix=is_appendix,
                appendix_letter=appendix_letter,
            )
            print(f"Обработаны стили таблиц для {md_path.name}")
        except Exception as e:
            print(f"Ошибка при добавлении стилей таблиц для {md_path.name}: {str(e)}")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_links_and_toc(md_path):
    md_path = Path(md_path)
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'[{m.group(1)}]({m.group(2).replace(" ", "%20")})',
            content,
        )

        toc_entries = []

        def make_anchor(match):
            level = len(match.group(1))
            title = match.group(2).strip()
            anchor = re.sub(r"[^\w\s-]", "", title.lower())
            anchor = re.sub(r"\s+", "-", anchor).strip("-")
            toc_entries.append((level, title, anchor))
            return f'<a id="{anchor}"></a>\n{match.group(0)}'

        content = re.sub(r"^(#+)\s+(.+)$", make_anchor, content, flags=re.MULTILINE)

        if toc_entries and "## Оглавление" in content:
            toc = "## Оглавление\n\n" + "\n".join(
                f"{'    ' * (level - 1)}- [{title}](#{anchor})"
                for level, title, anchor in toc_entries
            )
            content = re.sub(
                r"(## Оглавление\n\n).*?(\n## )",
                f"{toc}\\2",
                content,
                flags=re.DOTALL,
                count=1,
            )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Ошибка обработки оглавления: {str(e)}")


def replace_image_links(md_path, replacement_rules=None):
    md_path = Path(md_path)
    if not replacement_rules:
        return

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_md(match):
        alt = match.group(1)
        old_path = match.group(2)
        base = old_path.split("?")[0]
        new_path = replacement_rules.get(base, base) + old_path[len(base) :]
        return f"![{alt}]({new_path})"

    def replace_html(match):
        old_src = re.search(r'src="([^"]+)"', match.group(0)).group(1)
        base = old_src.split("?")[0]
        new_src = replacement_rules.get(base, base) + old_src[len(base) :]
        return match.group(0).replace(old_src, new_src)

    content = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_md, content)
    content = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', replace_html, content)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


import sys
import os
from pathlib import Path


def append_or_update_styles(
    md_path,
    project_root,
    has_images,
    has_tables,
    is_appendix=False,
    appendix_letter="А",
):
    md_path = Path(md_path)
    style_marker = "<!-- DOCX2MD STYLES -->"

    # Определяем базовый путь - для EXE или исходного кода
    base_path = Path(getattr(sys, "_MEIPASS", project_root))

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    styles = []
    if is_appendix:
        css_appendices_path = base_path / "src" / "css" / "styles_appendices.css"
        if css_appendices_path.exists():
            with open(css_appendices_path, "r", encoding="utf-8") as css_file:
                css_content = css_file.read().strip()
                css_content = css_content.replace(
                    "var(--appLetter)", f'"{appendix_letter}"'
                )
                styles.append(css_content)
        else:
            print(f"Файл {css_appendices_path} не найден")
    else:
        if has_images:
            css_images_path = base_path / "src" / "css" / "styles_images.css"
            if css_images_path.exists():
                with open(css_images_path, "r", encoding="utf-8") as css_file:
                    styles.append(css_file.read().strip())
            else:
                print(f"Файл {css_images_path} не найден")

        if has_tables:
            css_tables_path = base_path / "src" / "css" / "styles_tables.css"
            if css_tables_path.exists():
                with open(css_tables_path, "r", encoding="utf-8") as css_file:
                    styles.append(css_file.read().strip())
            else:
                print(f"Файл {css_tables_path} не найден")

    if styles:
        combined_styles = "\n".join(styles)

        if is_appendix:
            # Для приложений добавляем data-атрибут с буквой приложения
            style_tag = f'<style data-appendix="{appendix_letter}">\n{combined_styles}\n</style>'

            # Удаляем старые стили этого приложения, если они есть
            content = re.sub(
                rf'<style data-appendix="{appendix_letter}">.*?</style>',
                "",
                content,
                flags=re.DOTALL,
            )
        else:
            style_tag = f"<style>\n{combined_styles}\n</style>"
            # Удаляем только общие стили, если они есть
            if style_marker in content:
                content = re.sub(
                    r"(<!-- DOCX2MD STYLES -->\s*)<style>.*?</style>",
                    "",
                    content,
                    flags=re.DOTALL,
                )

        if is_appendix:
            # Для приложений добавляем без маркера
            content += f"\n\n{style_tag}"
        else:
            # Для обычных стилей добавляем с маркером
            if style_marker not in content:
                content += f"\n\n{style_marker}\n{style_tag}"
            else:
                content = content.replace(style_marker, f"{style_marker}\n{style_tag}")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
