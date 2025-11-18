import requests
import re
from pathlib import Path
from datetime import datetime
from tagger.smart_tagger import SmartTagger
import logging
from typing import Dict, List
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ API-ЗАГОЛОВКОВ ===
def _api_headers(headers: Dict) -> Dict:
    """Добавляет Accept: application/json для всех API-запросов."""
    h = headers.copy()
    h["Accept"] = "application/json"
    return h


# === ПОЛКИ (SHELVES) ===
def get_shelves(base_url: str, headers: dict) -> list | None:
    """Получить список полок."""
    try:
        resp = requests.get(
            f"{base_url}/api/shelves", headers=_api_headers(headers), timeout=30
        )
        if resp.status_code != 200:
            logger.error(
                f"Ошибка получения полок: {resp.status_code} {resp.text[:500]}"
            )
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

        existing = next((s for s in shelves if s["name"] == shelf_name), None)
        if existing:
            return existing["id"]

        payload = {
            "name": shelf_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/shelves",
            headers=_api_headers(headers),
            json=payload,
            timeout=30,
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
            f"{base_url}/api/shelves/{shelf_id}",
            headers=_api_headers(headers),
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"Ошибка получения книг в полке {shelf_id}: {resp.text[:500]}")
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
        logger.info(f"Поиск/создание книги '{book_name}' в полке {shelf_id}")

        # Сначала пытаемся найти книгу по имени во всех книгах
        all_books_resp = requests.get(
            f"{base_url}/api/books", headers=_api_headers(headers), timeout=30
        )
        if all_books_resp.ok:
            all_books = all_books_resp.json().get("data", [])
            existing_in_all = next(
                (b for b in all_books if b["name"] == book_name), None
            )
            if existing_in_all:
                logger.info(f"Найдена существующая книга: {existing_in_all['id']}")
                # Проверяем, есть ли книга уже в полке
                shelf_books = get_books_in_shelf(base_url, headers, shelf_id)
                if shelf_books:
                    existing_in_shelf = next(
                        (b for b in shelf_books if b["id"] == existing_in_all["id"]),
                        None,
                    )
                    if not existing_in_shelf:
                        logger.info(
                            f"Добавляем книгу {existing_in_all['id']} в полку {shelf_id}"
                        )
                        # Добавляем существующую книгу в полку
                        current_book_ids = [b["id"] for b in shelf_books]
                        current_book_ids.append(existing_in_all["id"])
                        update_resp = requests.put(
                            f"{base_url}/api/shelves/{shelf_id}",
                            headers=_api_headers(headers),
                            json={"books": current_book_ids},
                            timeout=30,
                        )
                        if update_resp.status_code != 200:
                            logger.warning(
                                f"Не удалось добавить книгу в полку: {update_resp.text}"
                            )
                return existing_in_all["id"]

        # Если книга не найдена, создаем новую
        logger.info(f"Создание новой книги: {book_name}")
        payload = {
            "name": book_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/books",
            headers=_api_headers(headers),
            json=payload,
            timeout=30,
        )
        if resp.status_code not in [200, 201]:
            logger.error(f"Ошибка создания книги: {resp.text}")
            return None

        book_id = resp.json()["id"]
        logger.info(f"Создана новая книга: ID {book_id}")

        # Добавляем книгу в полку
        shelf_books = get_books_in_shelf(base_url, headers, shelf_id) or []
        current_book_ids = [b["id"] for b in shelf_books]
        if book_id not in current_book_ids:
            current_book_ids.append(book_id)
            update_resp = requests.put(
                f"{base_url}/api/shelves/{shelf_id}",
                headers=_api_headers(headers),
                json={"books": current_book_ids},
                timeout=30,
            )
            if update_resp.status_code != 200:
                logger.error(
                    f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось добавить книгу в полку: {update_resp.text}"
                )
                # Но все равно возвращаем ID книги - она создана, просто не в полке

        return book_id

    except Exception as e:
        logger.exception(f"Исключение в create_or_get_book_in_shelf: {e}")
        return None


# === ГЛАВЫ (CHAPTERS) ===
def create_or_get_chapter(
    base_url: str, headers: dict, book_id: int, chapter_name: str
) -> int | None:
    try:
        logger.info(f"Поиск/создание главы '{chapter_name}' в книге {book_id}")

        # Сначала пытаемся найти главу в указанной книге
        resp = requests.get(
            f"{base_url}/api/chapters?book_id={book_id}",
            headers=_api_headers(headers),
            timeout=30,
        )
        if not resp.ok:
            logger.error(f"Ошибка получения глав для книги {book_id}: {resp.text}")
            return None

        chapters = resp.json().get("data", [])
        logger.info(f"Найдено глав в книге {book_id}: {len(chapters)}")

        # Ищем главу по имени
        existing = None
        for chapter in chapters:
            if chapter.get("name") == chapter_name:
                existing = chapter
                break

        if existing:
            existing_id = existing["id"]
            existing_book_id = existing.get("book_id")
            logger.info(
                f"Найдена существующая глава '{chapter_name}' в книге {book_id}: ID {existing_id} (принадлежит книге {existing_book_id})"
            )

            # Дополнительная проверка: убедимся, что глава действительно принадлежит указанной книге
            if existing_book_id != book_id:
                logger.warning(
                    f"НЕСООТВЕТСТВИЕ: Глава {existing_id} принадлежит книге {existing_book_id}, а не {book_id}. Игнорируем."
                )
                existing = None

        if existing:
            return existing["id"]

        # Если глава не найдена в указанной книге, создаем новую
        logger.info(f"Создание новой главы '{chapter_name}' в книге {book_id}")
        payload = {
            "book_id": book_id,
            "name": chapter_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d')}",
        }

        resp = requests.post(
            f"{base_url}/api/chapters",
            headers=_api_headers(headers),
            json=payload,
            timeout=30,
        )

        if resp.ok:
            new_chapter_data = resp.json()
            new_chapter_id = new_chapter_data["id"]
            new_chapter_book_id = new_chapter_data.get("book_id")

            logger.info(
                f"Создана новая глава: ID {new_chapter_id} в книге {new_chapter_book_id}"
            )

            # Проверяем, что глава создана в правильной книге
            if new_chapter_book_id != book_id:
                logger.error(
                    f"ОШИБКА: Глава создана в книге {new_chapter_book_id} вместо {book_id}!"
                )
                return None

            return new_chapter_id

        logger.error(f"Ошибка создания главы: {resp.status_code} - {resp.text}")
        return None

    except Exception as e:
        logger.exception(f"Ошибка в create_or_get_chapter: {e}")
        return None


# === ЗАГРУЗКА MD С ИЗОБРАЖЕНИЯМИ ===
def upload_md_with_images(
    base_url: str,
    headers: dict,
    book_id: int,
    md_path: str,
    images_dir: str = "images",
    log_callback=None,
    auto_tags: bool = True,
    chapter_id: int = None,
) -> bool:
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

        tags_for_api = []
        if auto_tags:
            try:
                tagger = SmartTagger()
                raw_tags = tagger.get_document_tags(md_path, md_content)
                tags_for_api = [{"name": t, "value": ""} for t in raw_tags]
                if log_callback:
                    log_callback(f"Теги: {', '.join(raw_tags)}", "gray")
            except Exception as e:
                if log_callback:
                    log_callback(f"Тегирование не удалось: {e}", "orange")

        # === КРИТИЧЕСКИ ВАЖНО: Обработка главы ===
        final_chapter_id = None
        chapter_name = None

        if chapter_id:
            # Получаем информацию о главе
            chapter_resp = requests.get(
                f"{base_url}/api/chapters/{chapter_id}",
                headers=_api_headers(headers),
                timeout=30,
            )
            if chapter_resp.ok:
                chapter_data = chapter_resp.json()
                chapter_book_id = chapter_data.get("book_id")
                chapter_name = chapter_data.get("name", "Unknown")

                if chapter_book_id != book_id:
                    if log_callback:
                        log_callback(
                            f"Глава '{chapter_name}' принадлежит книге ID {chapter_book_id}, а не выбранной книге ID {book_id}",
                            "orange",
                        )
                        log_callback(
                            f"Создаем новую главу '{chapter_name}' в выбранной книге",
                            "blue",
                        )

                    # Создаем новую главу с тем же именем в нужной книге
                    new_chapter_id = create_or_get_chapter(
                        base_url, headers, book_id, chapter_name
                    )
                    if new_chapter_id:
                        # НЕМЕДЛЕННАЯ ПРОВЕРКА новой главы
                        verify_resp = requests.get(
                            f"{base_url}/api/chapters/{new_chapter_id}",
                            headers=_api_headers(headers),
                            timeout=30,
                        )
                        if verify_resp.ok:
                            verify_data = verify_resp.json()
                            verify_book_id = verify_data.get("book_id")
                            if verify_book_id == book_id:
                                final_chapter_id = new_chapter_id
                                if log_callback:
                                    log_callback(
                                        f"✅ Создана новая глава ID: {new_chapter_id} в книге {book_id}",
                                        "green",
                                    )
                            else:
                                if log_callback:
                                    log_callback(
                                        f"❌ Новая глава создана в неправильной книге {verify_book_id} вместо {book_id}",
                                        "red",
                                    )
                                final_chapter_id = None
                        else:
                            if log_callback:
                                log_callback(
                                    f"❌ Не удалось проверить созданную главу", "red"
                                )
                            final_chapter_id = None
                    else:
                        if log_callback:
                            log_callback(
                                f"❌ Не удалось создать главу в выбранной книге. Загружаем без главы.",
                                "red",
                            )
                else:
                    final_chapter_id = chapter_id
                    if log_callback:
                        log_callback(
                            f"✅ Глава '{chapter_name}' принадлежит выбранной книге",
                            "green",
                        )
            else:
                if log_callback:
                    log_callback(
                        f"⚠️ Не удалось получить информацию о главе {chapter_id}. Загружаем без главы.",
                        "orange",
                    )

        # === ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся, что final_chapter_id принадлежит правильной книге ===
        if final_chapter_id:
            verify_resp = requests.get(
                f"{base_url}/api/chapters/{final_chapter_id}",
                headers=_api_headers(headers),
                timeout=30,
            )
            if verify_resp.ok:
                verify_data = verify_resp.json()
                verify_book_id = verify_data.get("book_id")
                if verify_book_id != book_id:
                    if log_callback:
                        log_callback(
                            f"ОШИБКА ВЕРИФИКАЦИИ: Глава ID {final_chapter_id} принадлежит книге {verify_book_id} вместо {book_id}",
                            "red",
                        )
                    final_chapter_id = None
            else:
                if log_callback:
                    log_callback(
                        f"Не удалось проверить главу ID {final_chapter_id}", "orange"
                    )
                final_chapter_id = None

        if log_callback:
            log_callback(f"Создание страницы в книге ID: {book_id}", "#00ffff")
            if final_chapter_id:
                log_callback(f"В главе ID: {final_chapter_id}", "#00ffff")
            else:
                log_callback(f"Без главы", "#00ffff")

        payload = {
            "name": page_name,
            "book_id": book_id,
            "markdown": md_content,
            "priority": 1,
            "draft": False,
            "tags": tags_for_api,
        }
        if final_chapter_id:
            payload["chapter_id"] = final_chapter_id

        if log_callback:
            log_callback(
                f"Payload: книга={book_id}, имя={page_name}, глава={final_chapter_id}",
                "gray",
            )

        resp = requests.post(
            f"{base_url}/api/pages",
            headers=_api_headers(headers),
            json=payload,
            timeout=30,
        )

        if not resp.ok:
            error_msg = f"Ошибка создания страницы: {resp.status_code} - {resp.text}"
            if log_callback:
                log_callback(error_msg, "red")
            logger.error(error_msg)
            return False

        page_data = resp.json()
        page_id = page_data["id"]
        actual_book_id = page_data.get("book_id")

        # Финальная проверка
        if actual_book_id != book_id:
            error_msg = f"КРИТИЧЕСКАЯ ОШИБКА: BookStack API проигнорировал book_id! Страница создана в книге ID {actual_book_id} вместо {book_id}!"
            if log_callback:
                log_callback(error_msg, "red")
            logger.error(error_msg)

            # Пытаемся удалить неправильно созданную страницу
            try:
                delete_resp = requests.delete(
                    f"{base_url}/api/pages/{page_id}",
                    headers=_api_headers(headers),
                    timeout=30,
                )
                if delete_resp.ok:
                    log_callback(
                        f"Удалена неправильно созданная страница ID {page_id}", "orange"
                    )
                else:
                    log_callback(
                        f"Не удалось удалить неправильную страницу: {delete_resp.text}",
                        "orange",
                    )
            except Exception as e:
                log_callback(
                    f"Ошибка при удалении неправильной страницы: {e}", "orange"
                )

            return False

        if log_callback:
            log_callback(f"Создана страница: {page_name} (ID: {page_id})", "green")
            log_callback(f"Успешно в книге ID: {actual_book_id}", "green")

        # === Изображения ===
        local_images = []
        html_images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', md_content, re.I)
        markdown_images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", md_content)
        for src in html_images:
            if not src.startswith(("http://", "https://", "/", "data:", "#")):
                local_images.append((src, False))
        for alt, src in markdown_images:
            if not src.startswith(("http://", "https://", "/", "data:", "#")):
                local_images.append((src, True))

        if not local_images:
            return True

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

        # === Замена ссылок ===
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

        # === Обновление страницы ===
        update_resp = requests.put(
            f"{base_url}/api/pages/{page_id}",
            headers=_api_headers(headers),
            json={"markdown": updated_md},
            timeout=30,
        )

        if update_resp.ok:
            if log_callback:
                log_callback(f"Обновлено: {uploaded}/{total} изображений", "#00ffff")
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
