# src/converter/bookstack_api.py
import requests
import re
from pathlib import Path
from datetime import datetime
from tagger.smart_tagger import SmartTagger
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# === ПОЛКИ (SHELVES) ===
def get_shelves(base_url: str, headers: dict) -> list | None:
    """Получить список полок."""
    try:
        resp = requests.get(f"{base_url}/api/shelves", headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Ошибка получения полок: {resp.status_code} {resp.text}")
            return None
        return resp.json().get("data", [])
    except Exception as e:
        logger.exception(f"Исключение в get_shelves: {e}")
        return None


def create_or_get_shelf(base_url: str, headers: dict, shelf_name: str) -> int | None:
    """Создать полку или вернуть ID существующей."""
    try:
        shelves = get_shelves(base_url, headers)
        if not shelves:
            return None

        # Поиск существующей
        existing = next((s for s in shelves if s["name"] == shelf_name), None)
        if existing:
            return existing["id"]

        # Создание новой
        payload = {
            "name": shelf_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/shelves", headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in [200, 201]:
            logger.error(f"Ошибка создания полки: {resp.text}")
            return None
        return resp.json()["id"]
    except Exception as e:
        logger.exception(f"Исключение в create_or_get_shelf: {e}")
        return None


# === КНИГИ (BOOKS) ===
def get_books_in_shelf(base_url: str, headers: dict, shelf_id: int) -> list | None:
    """Получить книги в полке."""
    try:
        resp = requests.get(
            f"{base_url}/api/shelves/{shelf_id}", headers=headers, timeout=30
        )
        if resp.status_code != 200:
            logger.error(f"Ошибка получения книг в полке {shelf_id}: {resp.text}")
            return None
        return resp.json().get("books", [])
    except Exception as e:
        logger.exception(f"Исключение в get_books_in_shelf: {e}")
        return None


def create_or_get_book_in_shelf(
    base_url: str, headers: dict, shelf_id: int, book_name: str
) -> int | None:
    """Создать книгу или вернуть ID существующей."""
    try:
        books = get_books_in_shelf(base_url, headers, shelf_id)
        if books is None:
            return None

        # Поиск существующей
        existing = next((b for b in books if b["name"] == book_name), None)
        if existing:
            return existing["id"]

        # Создание новой книги
        payload = {
            "name": book_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/books", headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in [200, 201]:
            logger.error(f"Ошибка создания книги: {resp.text}")
            return None

        book_id = resp.json()["id"]

        # Добавление книги в полку
        current_book_ids = [b["id"] for b in books]
        if book_id not in current_book_ids:
            current_book_ids.append(book_id)
            update_resp = requests.put(
                f"{base_url}/api/shelves/{shelf_id}",
                headers=headers,
                json={"books": current_book_ids},
                timeout=30,
            )
            if update_resp.status_code != 200:
                logger.warning(f"Не удалось обновить полку: {update_resp.text}")

        return book_id
    except Exception as e:
        logger.exception(f"Исключение в create_or_get_book_in_shelf: {e}")
        return None


# === ЗАГРУЗКА СТРАНИЦЫ + ИЗОБРАЖЕНИЯ + АВТОТЕГИРОВАНИЕ ===
def upload_md_with_images(
    base_url: str,
    headers: dict,
    book_id: int,
    md_path: str,
    images_dir: str = "images",
    log_callback=None,
    auto_tags: bool = True,
) -> bool:
    """
    Загружает Markdown-страницу и изображения.
    Поддерживает:
      - Создание страницы
      - Загрузку изображений через Gallery API
      - Замену ссылок
      - Автоматическое тегирование (если auto_tags=True)
    """
    md_path = Path(md_path)
    if not md_path.exists():
        if log_callback:
            log_callback(f"Файл не найден: {md_path}", "red")
        return False

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        page_name = md_path.stem
        img_folder = md_path.parent / images_dir

        # === 1. АВТОТЕГИРОВАНИЕ ===
        tags_for_api = []
        if auto_tags:
            try:
                tagger = SmartTagger()
                raw_tags = tagger.get_document_tags(md_path, md_content)
                tags_for_api = [{"name": tag, "value": ""} for tag in raw_tags]
                if log_callback:
                    log_callback(f"Теги: {', '.join(raw_tags)}", "blue")
            except Exception as e:
                logger.warning(f"Ошибка тегирования {md_path.name}: {e}")
                if log_callback:
                    log_callback(f"Тегирование не удалось: {e}", "orange")

        # === 2. Создание страницы ===
        payload = {
            "name": page_name,
            "book_id": book_id,
            "markdown": md_content,
            "priority": 1,
            "draft": False,
            "tags": tags_for_api,  # ← Добавлено
        }
        resp = requests.post(
            f"{base_url}/api/pages", headers=headers, json=payload, timeout=30
        )
        if not resp.ok:
            error_msg = f"Ошибка создания страницы: {resp.text}"
            if log_callback:
                log_callback(error_msg, "red")
            logger.error(error_msg)
            return False

        page_id = resp.json()["id"]
        if log_callback:
            log_callback(f"Страница создана: {page_name} (ID: {page_id})", "blue")

        # === 3. Поиск локальных изображений ===
        html_images = re.findall(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', md_content, re.IGNORECASE
        )
        markdown_images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", md_content)

        local_images = []
        for src in html_images:
            if not src.startswith(("http://", "https://", "/", "data:", "#")):
                local_images.append((src, False))
        for alt, src in markdown_images:
            if not src.startswith(("http://", "https://", "/", "data:", "#")):
                local_images.append((src, True))

        if not local_images:
            return True  # Страница создана, изображения не нужны

        # === 4. Загрузка изображений ===
        replacement_map = {}
        total = len(local_images)
        uploaded = 0

        for src, is_markdown in local_images:
            img_name = Path(src).name
            img_path = img_folder / img_name
            if not img_path.exists():
                if log_callback:
                    log_callback(f"Изображение не найдено: {img_path}", "orange")
                continue

            if log_callback:
                log_callback(f"Загрузка: {img_name}", "gray")

            try:
                with open(img_path, "rb") as f:
                    files = {"image": (img_name, f, "image/png")}
                    data = {"type": "gallery", "uploaded_to": page_id}
                    gallery_resp = requests.post(
                        f"{base_url}/api/image-gallery",
                        headers={"Authorization": headers["Authorization"]},
                        files=files,
                        data=data,
                        timeout=30,
                    )

                if not gallery_resp.ok:
                    error_msg = f"Ошибка загрузки {img_name}: {gallery_resp.text}"
                    if log_callback:
                        log_callback(error_msg, "red")
                    logger.error(error_msg)
                    continue

                gallery_url = gallery_resp.json().get("url")
                if not gallery_url:
                    if log_callback:
                        log_callback(f"Нет URL для {img_name}", "red")
                    continue

                replacement_map[src] = gallery_url
                uploaded += 1
                if log_callback:
                    log_callback(f"Успешно: {img_name}", "green")

            except Exception as e:
                if log_callback:
                    log_callback(f"Ошибка файла {img_name}: {e}", "red")
                logger.exception(f"Ошибка загрузки изображения: {e}")

        if not replacement_map:
            return True

        # === 5. Замена ссылок ===
        def replace_html_img(match):
            full = match.group(0)
            old = match.group(1)
            new = replacement_map.get(old, old)
            return re.sub(r'src=["\'][^"\']+["\']', f'src="{new}"', full, 1)

        updated_md = re.sub(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
            replace_html_img,
            md_content,
            flags=re.IGNORECASE,
        )

        updated_md = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: f"![{m.group(1)}]({replacement_map.get(m.group(2), m.group(2))})",
            updated_md,
        )

        # === 6. Обновление страницы ===
        update_resp = requests.put(
            f"{base_url}/api/pages/{page_id}",
            headers=headers,
            json={"markdown": updated_md},
            timeout=30,
        )

        if update_resp.ok:
            if log_callback:
                log_callback(f"Обновлено: {uploaded}/{total} изображений", "blue")
            return True
        else:
            error_msg = f"Ошибка обновления страницы: {update_resp.text}"
            if log_callback:
                log_callback(error_msg, "red")
            logger.error(error_msg)
            return False

    except Exception as e:
        error_msg = f"Критическая ошибка при загрузке {md_path.name}: {e}"
        if log_callback:
            log_callback(error_msg, "red")
        logger.exception(error_msg)
        return False
