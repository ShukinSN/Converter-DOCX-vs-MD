import os
import re
import shutil
from datetime import datetime
from wand.image import Image
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="wand.*")


def sanitize_filename(name):
    """Очистка имени файла от недопустимых символов."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def convert_emf_to_png(emf_path):
    """Конвертация EMF в PNG с обработкой ошибок."""
    try:
        png_path = os.path.splitext(emf_path)[0] + ".png"
        with Image(filename=emf_path) as img:
            img.format = "png"
            img.save(filename=png_path)
        return png_path
    except Exception as e:
        print(f"Ошибка конвертации {emf_path} в PNG: {str(e)}")
        return None


def process_images(md_path, temp_dir):
    """Основная функция обработки изображений и подписей."""
    md_dir = os.path.dirname(md_path)
    images_folder = os.path.join(md_dir, "images")
    os.makedirs(images_folder, exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    figure_counter = 1
    lines = content.split("\n")
    new_lines = []
    i = 0
    in_table = False

    # Упрощенные стили только для центрирования изображений
    css = """<style>
.figure-container {
    text-align: center;
    margin: 15px 0;
}
.figure-container img {
    display: inline-block;
    max-width: 100%;
    height: auto;
}
.figure-caption {
    display: block;
    text-align: center;
    font-style: italic;
    margin-top: 5px;
}
.figure-caption:before {
    content: "Рисунок " counter(figureCounter) " - ";
    font-weight: bold;
}
body {
    counter-reset: figureCounter;
}
.figure-container {
    counter-increment: figureCounter;
}
</style>"""

    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        # Определяем, находимся ли мы внутри таблицы
        if not in_table and stripped_line.startswith("|") and "|" in stripped_line[1:]:
            in_table = True
        elif in_table and not stripped_line.startswith("|"):
            in_table = False

        # Обработка изображений (как в таблицах, так и вне их)
        def process_image_match(match, is_markdown=True):
            nonlocal line
            src = match.group(2 if is_markdown else 1)
            if src.startswith("data:") or not src.strip():
                return None

            original_name = os.path.basename(src.split("?")[0])
            name, ext = os.path.splitext(original_name)
            img_name = f"{name}_{timestamp}{ext.lower()}"
            img_name = sanitize_filename(img_name)

            possible_paths = [
                os.path.join(temp_dir, "media", original_name),
                os.path.join(temp_dir, original_name),
                os.path.join(md_dir, original_name),
            ]
            src_path = next((p for p in possible_paths if os.path.exists(p)), None)

            if not src_path:
                return None

            if src_path.lower().endswith(".emf"):
                png_path = convert_emf_to_png(src_path)
                if png_path:
                    src_path = png_path
                    img_name = f"{name}_{timestamp}.png"
                    ext = ".png"

            file_counter = 1
            while os.path.exists(os.path.join(images_folder, img_name)):
                base_name = os.path.splitext(img_name)[0]
                if "_" in base_name:
                    base_name = base_name.rsplit("_", 1)[0]
                img_name = f"{base_name}_{file_counter}{ext}"
                file_counter += 1

            dest_path = os.path.join(images_folder, img_name)
            shutil.copy2(src_path, dest_path)
            rel_path = os.path.relpath(dest_path, md_dir).replace("\\", "/")

            if is_markdown:
                line = line.replace(src, rel_path)
            else:
                line = re.sub(
                    r'src="' + re.escape(src) + r'"', f'src="{rel_path}"', line
                )

            return rel_path

        # Обработка изображений вне таблиц
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
                                r"^(?:Рисунок|Рис\.?)\s*(?:\d+)?\s*[–—-]\s*(.*)$",
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

        # Обработка изображений внутри таблиц (без изменений)
        md_images = list(re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", line))
        for match in md_images:
            process_image_match(match, is_markdown=True)

        html_images = list(re.finditer(r'<img\s+[^>]*src="([^"]+)"[^>]*>', line))
        for match in html_images:
            process_image_match(match, is_markdown=False)

        # Пропускаем строки с подписями без изображений
        if not in_table and re.match(
            r"^(?:Рисунок|Рис\.?)\s*[–—-]", stripped_line, re.IGNORECASE
        ):
            i += 1
        else:
            new_lines.append(line)
            i += 1

    content = "\n".join(new_lines)
    if "<style>" not in content:
        content = css + "\n\n" + content

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_links_and_toc(md_path):
    """Функция для обработки ссылок и создания оглавления."""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Исправление пробелов в ссылках
        content = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'[{m.group(1)}]({m.group(2).replace(" ", "%20")})',
            content,
        )

        # Создание якорей и оглавления
        toc_entries = []

        def make_anchor(match):
            level = len(match.group(1))
            title = match.group(2).strip()
            anchor = re.sub(r"[^\w\s-]", "", title.lower())
            anchor = re.sub(r"\s+", "-", anchor).strip("-")
            toc_entries.append((level, title, anchor))
            return f'<a id="{anchor}"></a>\n{match.group(0)}'

        content = re.sub(r"^(#+)\s+(.+)$", make_anchor, content, flags=re.MULTILINE)

        # Вставка оглавления
        if "## Оглавление" in content:
            toc = "## Оглавление\n\n" + "\n".join(
                f"{'    '*(l-1)}- [{t}](#{a})" for l, t, a in toc_entries
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
    """Замена ссылок на изображения по правилам."""
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
