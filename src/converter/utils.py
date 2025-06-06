import os
import re
import shutil
from datetime import datetime
from wand.image import Image
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="wand.*")


def sanitize_filename(name):  # Очищает имя файла от недопустимых символов.
    return re.sub(
        r'[\\/*?:"<>|]', "_", name
    )  # это выражение "очищает" строку, заменяя недопустимые символы на подчёркивания.


def convert_emf_to_png(emf_path):  # Конвертирует файл EMF в PNG с помощью Wand.

    try:
        png_path = os.path.splitext(emf_path)[0] + ".png"
        with Image(filename=emf_path) as img:
            img.format = "png"
            img.save(filename=png_path)
        return png_path
    except Exception as e:
        raise Exception(f"Ошибка конвертации EMF в PNG: {str(e)}")


def process_images(
    md_path, temp_dir
):  # Обработка изображений в Markdown файле, перемещение их в папку images и обновление ссылок.

    md_dir = os.path.dirname(md_path)
    images_folder = os.path.join(md_dir, "images")
    os.makedirs(images_folder, exist_ok=True)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    image_counter = {}  # Словарь для подсчёта одинаковых alt_text

    img_patterns = [
        (r"!\[([^\]]*)\]\(([^)]+)\)", True),  # поиск изображений в Markdown
        (r'<img[^>]+src="([^"]+)"[^>]*>', False),  # поиск изображений в HTML
    ]
    for pattern, is_markdown in img_patterns:

        def replacer(match):
            src = match.group(2 if is_markdown else 1)
            if src.startswith("data:") or not src.strip():
                return match.group(0)

            original_name = os.path.basename(src.split("?")[0])
            name, ext = os.path.splitext(original_name)

            # Извлечение alt_text
            alt_text = match.group(1) if is_markdown and match.group(1) else None
            if not alt_text:
                # Если alt_text отсутствует, используем имя файла или подпись
                alt_text = (
                    os.path.splitext(original_name)[0].replace("_", " ").title()
                    or "Изображение"
                )

            base_name = sanitize_filename(alt_text)

            # Подсчёт уникальности для одинаковых alt_text
            if base_name in image_counter:
                image_counter[base_name] += 1
                img_name = f"{base_name}_{image_counter[base_name]}{ext.lower()}"
            else:
                image_counter[base_name] = 0
                img_name = f"{base_name}{ext.lower()}"

            possible_paths = [
                os.path.join(temp_dir, "media", original_name),
                os.path.join(temp_dir, original_name),
            ]

            src_path = next(
                (path for path in possible_paths if os.path.exists(path)), None
            )
            if not src_path:
                return match.group(0)

            if src_path.lower().endswith(".emf"):
                png_path = convert_emf_to_png(src_path)
                if png_path:
                    src_path = png_path
                    img_name = os.path.splitext(img_name)[0] + ".png"

            counter = 1
            while os.path.exists(os.path.join(images_folder, img_name)):
                img_name = f"{base_name}_{counter}{ext.lower()}"
                counter += 1

            dest_path = os.path.join(images_folder, img_name)
            shutil.copy2(src_path, dest_path)
            rel_path = os.path.relpath(dest_path, md_dir).replace("\\", "/")

            # Формируем только изображение без подписи и якоря
            if is_markdown:
                style = ""
                if match.group(0).find("style=") != -1:
                    style_match = re.search(r'style="([^"]*)"', match.group(0))
                    if style_match:
                        style = f' style="{style_match.group(1)}"'
                return f"![{alt_text}]({rel_path}{style})"
            else:
                style = re.search(r'style="([^"]*)"', match.group(0))
                style_str = f' style="{style.group(1)}"' if style else ""
                return f'<img src="{rel_path}"{style_str}>'

        content = re.sub(pattern, replacer, content, flags=re.IGNORECASE)

    # Удаляем строки вида "Рисунок X – ..." и связанные с ними упоминания
    content = re.sub(r"Рисунок \d+ – [^\n]+\n", "", content)
    content = re.sub(r"Рисунок \d+\.\n", "", content)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_links_and_toc(
    md_path,
):  # Исправление ссылок и оглавления в Markdown файле.

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Нормализация ссылок
    content = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'[{m.group(1)}]({m.group(2).replace(" ", "%20")})',
        content,  # Этот код исправляет Markdown-ссылки, заменяя пробелы в URL на %20, чтобы они корректно работали в браузерах и других системах.
    )

    # Исправление TOC
    toc_entries = []

    def toc_replacer(match):
        level = len(match.group(1))
        title = match.group(2).strip()
        anchor = re.sub(
            r"[^\w\s-]", "", title.lower(), flags=re.UNICODE
        )  # очищает строку от "лишних" символов
        anchor = re.sub(r"\s+", "-", anchor).strip(
            "-"
        )  # 1. Заменяет все пробельные последовательности на дефисы 2. Удаляет дефисы в начале и конце строки
        toc_entries.append((level, title, anchor))
        return f'<a id="{anchor}"></a>\n{match.group(0)}'

    content = re.sub(
        r"^(#+)\s+(.+)$", toc_replacer, content, flags=re.MULTILINE
    )  # Обработка заголовков

    # Обновление TOC, если оно есть
    toc_content = "## Оглавление\n\n" + "\n".join(
        f"{'    '*(level-1)}- [{title}](#{anchor})"
        for level, title, anchor in toc_entries
    )
    content = re.sub(
        r"(?s)(## Оглавление\n\n).*?(\n## )", f"{toc_content}\\2", content, count=1
    )

    # Пропускаем замену "Рисунок X", так как подписи удалены
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)


def replace_image_links(
    md_path, replacement_rules=None
):  # Замена ссылок на изображения по заданным правилам.

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    rules = replacement_rules or {}

    def md_replacer(match):
        alt_text = match.group(1)
        old_path = match.group(2)
        path_part = old_path.split("?")[0]
        params = old_path[len(path_part) :]
        new_path_part = rules.get(path_part, path_part)
        return f"![{alt_text}]({new_path_part}{params})"

    def html_replacer(match):
        old_path = match.group(1)
        path_part = old_path.split("?")[0]
        params = old_path[len(path_part) :]
        new_path_part = rules.get(path_part, path_part)
        return match.group(0).replace(old_path, new_path_part + params)

    content = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)", md_replacer, content
    )  # замена ссылок в Markdown
    content = re.sub(
        r'<img[^>]+src="([^"]+)"[^>]*>', html_replacer, content
    )  # замена ссылок в HTML

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
