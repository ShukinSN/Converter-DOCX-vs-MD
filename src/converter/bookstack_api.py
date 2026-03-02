# converter/bookstack_api.py — ПОЛНАЯ РАБОЧАЯ ВЕРСИЯ СО ВСЕМИ НУЖНЫМИ ФУНКЦИЯМИ
import requests
import re
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ====================== ПОЛКИ ======================
def get_shelves(base_url: str, headers: dict) -> list | None:
    try:
        resp = requests.get(f"{base_url}/api/shelves", headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Ошибка получения полок: {resp.status_code} {resp.text}")
            return None
        return resp.json().get("data", [])
    except Exception as e:
        logger.exception(f"get_shelves: {e}")
        return None


def create_or_get_shelf(base_url: str, headers: dict, shelf_name: str) -> int | None:
    shelves = get_shelves(base_url, headers)
    if not shelves:
        return None
    existing = next((s for s in shelves if s["name"] == shelf_name), None)
    if existing:
        return existing["id"]

    payload = {
        "name": shelf_name,
        "description": f"Авто-создано {datetime.now():%Y-%m-%d %H:%M}",
    }
    resp = requests.post(
        f"{base_url}/api/shelves", headers=headers, json=payload, timeout=30
    )
    if resp.status_code not in (200, 201):
        logger.error(f"Ошибка создания полки: {resp.text}")
        return None
    return resp.json()["id"]


# ====================== КНИГИ ======================
def get_books_in_shelf(base_url: str, headers: dict, shelf_id: int) -> list | None:
    try:
        resp = requests.get(
            f"{base_url}/api/shelves/{shelf_id}", headers=headers, timeout=30
        )
        if resp.status_code != 200:
            logger.error(f"Ошибка получения книг полки {shelf_id}: {resp.text}")
            return None
        return resp.json().get("books", [])
    except Exception as e:
        logger.exception(f"get_books_in_shelf: {e}")
        return None


def create_or_get_book_in_shelf(
    base_url: str, headers: dict, shelf_id: int, book_name: str
) -> int | None:
    books = get_books_in_shelf(base_url, headers, shelf_id)
    if books is None:
        return None
    existing = next((b for b in books if b["name"] == book_name), None)
    if existing:
        return existing["id"]

    payload = {
        "name": book_name,
        "description": f"Авто-создано {datetime.now():%Y-%m-%d %H:%M}",
    }
    resp = requests.post(
        f"{base_url}/api/books", headers=headers, json=payload, timeout=30
    )
    if resp.status_code not in (200, 201):
        logger.error(f"Ошибка создания книги: {resp.text}")
        return None

    book_id = resp.json()["id"]
    current_ids = [b["id"] for b in books]
    if book_id not in current_ids:
        current_ids.append(book_id)
        put_resp = requests.put(
            f"{base_url}/api/shelves/{shelf_id}",
            headers=headers,
            json={"books": current_ids},
            timeout=30,
        )
        if put_resp.status_code != 200:
            logger.warning(f"Не удалось привязать книгу к полке: {put_resp.text}")
    return book_id


# ====================== ГЛАВЫ (ЧАПТЕРЫ) ======================
def create_or_get_chapter(
    base_url: str, headers: dict, book_id: int, chapter_name: str
) -> int | None:
    """Создаёт главу в книге или возвращает существующую."""
    try:
        # Получаем все главы книги
        resp = requests.get(
            f"{base_url}/api/books/{book_id}?contains=chapters",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"Ошибка получения глав книги {book_id}: {resp.text}")
            return None

        chapters = resp.json().get("chapters", [])
        existing = next((c for c in chapters if c["name"] == chapter_name), None)
        if existing:
            return existing["id"]

        # Создаём новую главу
        payload = {
            "book_id": book_id,
            "name": chapter_name,
            "description": f"Авто-создана {datetime.now():%Y-%m-%d %H:%M}",
            "priority": 0,
        }
        resp = requests.post(
            f"{base_url}/api/chapters", headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Ошибка создания главы: {resp.text}")
            return None
        return resp.json()["id"]
    except Exception as e:
        logger.exception(f"create_or_get_chapter: {e}")
        return None


# ====================== СТРАНИЦЫ: ШАБЛОНЫ ======================
def get_book_pages(base_url: str, headers: dict, book_id: int) -> list | None:
    """
    Надёжно получает ВСЕ страницы книги (включая те, что внутри глав).
    Работает на всех версиях BookStack.
    """
    try:
        all_pages = []

        # 1. Страницы напрямую в книге (не в главах)
        resp = requests.get(
            f"{base_url}/api/books/{book_id}",
            headers=headers,
            params={"contains": "pages"},
            timeout=30,
        )
        if resp.status_code == 200:
            all_pages.extend(resp.json().get("pages", []))

        # 2. Страницы внутри глав
        resp_chapters = requests.get(
            f"{base_url}/api/books/{book_id}",
            headers=headers,
            params={"contains": "chapters,pages"},
            timeout=30,
        )
        if resp_chapters.status_code == 200:
            for chapter in resp_chapters.json().get("chapters", []):
                all_pages.extend(chapter.get("pages", []))

        # Убираем дубли по ID (на всякий случай)
        seen = set()
        unique_pages = []
        for page in all_pages:
            if page["id"] not in seen:
                seen.add(page["id"])
                unique_pages.append(page)

        logger.info(f"Получено {len(unique_pages)} страниц для книги ID {book_id}")
        return unique_pages

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при получении страниц книги {book_id}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Неожиданная ошибка в get_book_pages (книга {book_id}): {e}")
        return None


def mark_page_as_template(base_url: str, headers: dict, page_id: int) -> bool:
    try:
        resp = requests.put(
            f"{base_url}/api/pages/{page_id}",
            headers=headers,
            json={"template": True},
            timeout=30,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        logger.exception(f"mark_page_as_template: {e}")
        return False


# ====================== ЗАГРУЗКА СТРАНИЦЫ ======================
def upload_md_with_images(
    base_url: str,
    headers: dict,
    book_id: int,
    md_path: str,
    images_dir: str = "images",
    log_callback=None,
    auto_tags: bool = True,
    make_template: bool = False,
    chapter_id: int | None = None,
    manual_tags: list | None = None,  # Исправлено: list вместо list[str]
) -> bool:
    md_path = Path(md_path)
    if not md_path.exists():
        if log_callback:
            log_callback(f"Файл не найден: {md_path}", "red")
        return False

    try:
        md_content = md_path.read_text(encoding="utf-8")
        page_name = md_path.stem
        img_folder = md_path.parent / images_dir

        # === ТЕГИ: РУЧНЫЕ ИМЕЮТ ПРИОРИТЕТ ===
        tags = []
        if manual_tags:
            # manual_tags уже должен быть списком словарей
            tags = manual_tags
            if log_callback:
                # Безопасное преобразование словарей в строки для лога
                tag_strings = []
                for tag in manual_tags:
                    if isinstance(tag, dict):
                        tag_strings.append(
                            f"{tag.get('name', '')}:{tag.get('value', '')}"
                        )
                    else:
                        tag_strings.append(str(tag))
                log_callback(f"Ручные теги: {', '.join(tag_strings)}", "blue")
        elif auto_tags:
            try:
                from tagger.smart_tagger import SmartTagger

                tagger = SmartTagger()
                raw_tags = tagger.get_document_tags(md_path, md_content)
                tags = [
                    {"name": "system", "value": tag, "order": 0} for tag in raw_tags
                ]
                if log_callback:
                    log_callback(f"Авто-теги: {', '.join(raw_tags)}", "blue")
            except Exception as e:
                if log_callback:
                    log_callback(f"Ошибка тегирования: {e}", "orange")

        # === Создание страницы ===
        payload = {
            "name": page_name,
            "book_id": book_id,
            "markdown": md_content,
            "priority": 1,
            "draft": False,
            "tags": tags,
            "template": make_template,
        }
        if chapter_id:
            payload["chapter_id"] = chapter_id

        resp = requests.post(
            f"{base_url}/api/pages", headers=headers, json=payload, timeout=30
        )
        if not resp.ok:
            msg = f"Ошибка создания страницы: {resp.text}"
            if log_callback:
                log_callback(msg, "red")
            logger.error(msg)
            return False

        page_id = resp.json()["id"]
        status = " [ШАБЛОН]" if make_template else ""
        if log_callback:
            log_callback(
                f"Страница создана: {page_name} (ID: {page_id}){status}", "green"
            )

        # === Поиск и загрузка изображений ===
        local_refs = re.findall(
            r'!\[[^\]]*\]\(([^)]+)\)|<img[^>]+src=["\']([^"\'>]+)', md_content
        )
        local_refs = [
            ref
            for group in local_refs
            for ref in group
            if ref and not ref.startswith(("http", "/", "data:", "#"))
        ]

        if not local_refs:
            return True

        replacement_map = {}
        for ref in local_refs:
            img_name = Path(ref).name
            img_path = img_folder / img_name
            if not img_path.exists():
                if log_callback:
                    log_callback(f"Изображение не найдено: {img_path}", "orange")
                continue

            with open(img_path, "rb") as f:
                files = {"image": (img_name, f)}
                data = {"type": "gallery", "uploaded_to": page_id}
                r = requests.post(
                    f"{base_url}/api/image-gallery",
                    headers={"Authorization": headers["Authorization"]},
                    files=files,
                    data=data,
                    timeout=60,
                )

            if not r.ok:
                if log_callback:
                    log_callback(f"Ошибка загрузки {img_name}: {r.text}", "red")
                continue
            url = r.json().get("url")
            if url:
                replacement_map[ref] = url
                if log_callback:
                    log_callback(f"Загружено: {img_name}", "green")

        if replacement_map:
            updated_md = md_content
            for old, new in replacement_map.items():
                updated_md = updated_md.replace(f"({old})", f"({new})")
                updated_md = re.sub(
                    rf'(src=["\']){re.escape(old)}(["\'])',
                    rf"\1{new}\2",
                    updated_md,
                    flags=re.IGNORECASE,
                )

            update_payload = {"markdown": updated_md, "template": make_template}
            upd = requests.put(
                f"{base_url}/api/pages/{page_id}",
                headers=headers,
                json=update_payload,
                timeout=30,
            )
            if upd.ok and log_callback:
                log_callback(f"Страница обновлена с изображениями", "blue")

        return True

    except Exception as e:
        msg = f"Критическая ошибка: {e}"
        if log_callback:
            log_callback(msg, "red")
        logger.exception(msg)
        return False
