import re
import shutil
from pathlib import Path
from wand.image import Image
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="wand.*")


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def convert_emf_to_png(emf_path):
    try:
        png_path = Path(emf_path).with_suffix(".png")
        with Image(filename=str(emf_path)) as img:
            img.format = "png"
            img.save(filename=str(png_path))
        return png_path
    except Exception as e:
        print(f"Ошибка конвертации {emf_path} в PNG: {str(e)}")
        return None


def process_images(md_path, temp_dir, project_root):
    from datetime import datetime

    md_path = Path(md_path)
    md_dir = md_path.parent
    images_folder = md_dir / "images"
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
            nonlocal line, has_images
            src = match.group(2 if is_markdown else 1)
            if src.startswith("data:") or not src.strip():
                return None

            has_images = True
            original_name = Path(src.split("?")[0]).name
            name, ext = Path(original_name).stem, Path(original_name).suffix
            img_name = f"{name}_{timestamp}{ext.lower()}"
            img_name = sanitize_filename(img_name)

            possible_paths = [
                Path(temp_dir) / "media" / original_name,
                Path(temp_dir) / original_name,
                md_dir / original_name,
            ]
            src_path = next((p for p in possible_paths if p.exists()), None)

            if not src_path:
                return None

            if src_path.suffix.lower() == ".emf":
                png_path = convert_emf_to_png(src_path)
                if png_path:
                    src_path = png_path
                    img_name = f"{name}_{timestamp}.png"
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

        if not in_table:
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
                        for j in range(1, 4):
                            if i + j >= len(lines):
                                break
                            next_line = lines[i + j].strip()
                            caption_match = re.match(
                                r"^(?:Рисунок|Рис\.?)\s*(?:\d+)?\s*[-–—]\s*(.*)$",
                                next_line,
                                re.IGNORECASE,
                            )
                            if caption_match:
                                caption = caption_match.group(1).strip()
                                lines[i + j] = ""
                                break

                        if is_markdown:
                            line = f'<div class="figure-container">\n<img src="{rel_path}" alt="{img_match.group(1)}">\n<span class="figure-caption">{caption}</span>\n</div>'
                        else:
                            updated_img = re.sub(
                                r'\s*alt="[^"]*"', "", img_match.group(0)
                            )
                            updated_img = updated_img.replace(src, rel_path)
                            line = f'<div class="figure-container">\n{updated_img}\n<span class="figure-caption">{caption}</span>\n</div>'

        md_images = list(re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", line))
        for match in md_images:
            process_image_match(match, is_markdown=True)

        html_images = list(re.finditer(r'<img\s+[^>]*src="([^"]+)"[^>]*>', line))
        for match in html_images:
            process_image_match(match, is_markdown=False)

        if not in_table and re.match(
            r"^(?:Рисунок|Рис\.?)\s*[-–—]", stripped_line, re.IGNORECASE
        ):
            i += 1
        else:
            new_lines.append(line)
            i += 1

    content = "\n".join(new_lines)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def process_tables(md_path, project_root):
    md_path = Path(md_path)
    md_dir = md_path.parent
    project_root = Path(project_root)
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    new_lines = []
    i = 0
    in_table = False
    has_tables = False

    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        if not in_table and stripped_line.startswith("|") and "|" in stripped_line[1:]:
            in_table = True
            has_tables = True
        elif in_table and not stripped_line.startswith("|"):
            in_table = False

        if not in_table:
            caption_match = re.match(
                r"^(?:Таблица|Табл\.?)\s*(?:\d+)?\s*[-–—]\s*(.*)$",
                stripped_line,
                re.IGNORECASE,
            )
            if caption_match:
                caption = caption_match.group(1).strip()
                print(f"Найдена подпись таблицы: {stripped_line} -> {caption}")
                new_lines.append(f'<div class="table-caption">{caption}</div>')
                has_tables = True
                i += 1
                continue

        new_lines.append(line)
        i += 1

    content = "\n".join(new_lines)

    if has_tables:
        try:
            append_or_update_styles(
                md_path, project_root, has_images=False, has_tables=True
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


def append_or_update_styles(md_path, project_root, has_images, has_tables):
    md_path = Path(md_path)
    project_root = Path(project_root)
    style_marker = "<!-- DOCX2MD STYLES -->"

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    styles = []
    if has_images:
        css_images_path = project_root / "src" / "css" / "styles_images.css"
        if css_images_path.exists():
            with open(css_images_path, "r", encoding="utf-8") as css_file:
                styles.append(css_file.read().strip())
        else:
            print(f"Файл {css_images_path} не найден")

    if has_tables:
        css_tables_path = project_root / "src" / "css" / "styles_tables.css"
        if css_tables_path.exists():
            with open(css_tables_path, "r", encoding="utf-8") as css_file:
                styles.append(css_file.read().strip())
        else:
            print(f"Файл {css_tables_path} не найден")

    if styles:
        combined_styles = "\n".join(styles)
        if style_marker not in content:
            content += f"\n\n{style_marker}\n<style>\n{combined_styles}\n</style>"
        else:
            content = re.sub(
                r"(<!-- DOCX2MD STYLES -->\n<style>)(.*?)(</style>)",
                f"\\1{combined_styles}\n\\3",
                content,
                flags=re.DOTALL,
            )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
