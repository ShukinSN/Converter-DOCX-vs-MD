# converter/bookstack_api.py
import requests
import re
from pathlib import Path
from datetime import datetime


def get_shelves(base_url, headers):
    try:
        resp = requests.get(f"{base_url}/api/shelves", headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"Ошибка получения полок: {resp.text}")
            return None
        return resp.json().get("data", [])
    except Exception as e:
        print(f"Исключение при get_shelves: {str(e)}")
        return None


def get_books_in_shelf(base_url, headers, shelf_id):
    try:
        resp = requests.get(
            f"{base_url}/api/shelves/{shelf_id}", headers=headers, timeout=30
        )
        if resp.status_code != 200:
            print(f"Ошибка получения книг полки {shelf_id}: {resp.text}")
            return None
        return resp.json().get("books", [])
    except Exception as e:
        print(f"Исключение при get_books_in_shelf: {str(e)}")
        return None


def create_or_get_shelf(base_url, headers, shelf_name):
    try:
        shelves = get_shelves(base_url, headers)
        if not shelves:
            return None
        shelf = next((s for s in shelves if s["name"] == shelf_name), None)
        if shelf:
            return shelf["id"]

        payload = {
            "name": shelf_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/shelves", headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in [200, 201]:
            print(f"Ошибка создания полки: {resp.text}")
            return None
        return resp.json()["id"]
    except Exception as e:
        print(f"Исключение при create_or_get_shelf: {str(e)}")
        return None


def create_or_get_book_in_shelf(base_url, headers, shelf_id, book_name):
    try:
        books = get_books_in_shelf(base_url, headers, shelf_id)
        if books is None:
            return None
        book = next((b for b in books if b["name"] == book_name), None)
        if book:
            return book["id"]

        payload = {
            "name": book_name,
            "description": f"Авто-создано {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        }
        resp = requests.post(
            f"{base_url}/api/books", headers=headers, json=payload, timeout=30
        )
        if resp.status_code not in [200, 201]:
            print(f"Ошибка создания книги: {resp.text}")
            return None

        book_id = resp.json()["id"]
        current_ids = [b["id"] for b in books]
        if book_id not in current_ids:
            current_ids.append(book_id)
            update_resp = requests.put(
                f"{base_url}/api/shelves/{shelf_id}",
                headers=headers,
                json={"books": current_ids},
                timeout=30,
            )
            if update_resp.status_code != 200:
                print(f"Ошибка обновления полки: {update_resp.text}")
        return book_id
    except Exception as e:
        print(f"Исключение при create_or_get_book_in_shelf: {str(e)}")
        return None


def upload_md_with_images(
    base_url: str, headers: dict, book_id: int, md_path: str, images_dir: str = "images"
) -> bool:
    """
    Загружает изображения через /api/image-gallery с type='gallery'
    Заменяет <img src="images/..."> на <img src="https://.../gallery/...">
    """
    md_path = Path(md_path)
    if not md_path.exists():
        print(f"Файл не найден: {md_path}")
        return False

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        page_name = md_path.stem
        img_folder = md_path.parent / images_dir

        # === 1. Поиск локальных изображений ===
        html_images = re.findall(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', md_content, re.IGNORECASE
        )
        markdown_images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", md_content)

        local_images = []
        for src in html_images:
            if not src.startswith(("http", "https", "/", "data:", "#")):
                local_images.append((src, False))
        for alt, src in markdown_images:
            if not src.startswith(("http", "https", "/", "data:", "#")):
                local_images.append((src, True))

        # === 2. Создание страницы ===
        payload = {
            "name": page_name,
            "book_id": book_id,
            "markdown": md_content,
            "priority": 1,
            "draft": False,
        }
        resp = requests.post(
            f"{base_url}/api/pages", headers=headers, json=payload, timeout=30
        )
        if not resp.ok:
            print(f"Ошибка создания страницы: {resp.text}")
            return False

        page_id = resp.json()["id"]
        print(f"Страница создана: {page_name} (ID: {page_id})")

        if not local_images:
            return True

        # === 3. Загрузка через /api/image-gallery ===
        replacement_map = {}

        for src, is_markdown in local_images:
            img_name = Path(src).name
            img_path = img_folder / img_name
            if not img_path.exists():
                print(f"Изображение не найдено: {img_path}")
                continue

            files = {"image": (img_name, open(img_path, "rb"), "image/png")}
            data = {"type": "gallery", "uploaded_to": page_id}

            gallery_resp = requests.post(
                f"{base_url}/api/image-gallery",
                headers={"Authorization": headers["Authorization"]},
                files=files,
                data=data,
                timeout=30,
            )

            if not gallery_resp.ok:
                print(f"Ошибка загрузки в Gallery {img_name}: {gallery_resp.text}")
                continue

            gallery_data = gallery_resp.json()
            gallery_url = gallery_data.get("url")
            if not gallery_url:
                print(f"Нет URL в ответе для {img_name}: {gallery_data}")
                continue

            replacement_map[src] = gallery_url
            print(f"Загружено в Gallery: {img_name} → {gallery_url}")

        if not replacement_map:
            return True

        # === 4. Замена src в <img> ===
        def replace_img_src(match):
            full_tag = match.group(0)
            old_src = match.group(1)
            new_url = replacement_map.get(old_src, old_src)
            for quote in ['"', "'"]:
                old_attr = f"src={quote}{old_src}{quote}"
                new_attr = f"src={quote}{new_url}{quote}"
                if old_attr in full_tag:
                    full_tag = full_tag.replace(old_attr, new_attr, 1)
                    break
            return full_tag

        updated_md = re.sub(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>',
            replace_img_src,
            md_content,
            flags=re.IGNORECASE,
        )

        # === 5. Замена Markdown (если были) ===
        def replace_md_path(match):
            alt, old_src = match.groups()
            new_url = replacement_map.get(old_src, old_src)
            return f"![{alt}]({new_url})"

        updated_md = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_md_path, updated_md)

        # === 6. Обновление страницы ===
        update_resp = requests.put(
            f"{base_url}/api/pages/{page_id}",
            headers=headers,
            json={"markdown": updated_md},
            timeout=30,
        )

        if update_resp.ok:
            print("Страница обновлена: изображения через Gallery API")
            return True
        else:
            print(f"Ошибка обновления: {update_resp.text}")
            return False

    except Exception as e:
        print(f"Ошибка при загрузке {md_path.name}: {str(e)}")
        return False
