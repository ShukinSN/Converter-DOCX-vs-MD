import requests
import json
import markdown
from pathlib import Path
from datetime import datetime


def get_shelves(base_url, headers):
    """Получить список всех полок."""
    try:
        shelves_resp = requests.get(f"{base_url}/api/shelves", headers=headers)
        if shelves_resp.status_code != 200:
            print(f"Ошибка получения полок: {shelves_resp.text}")
            return None
        return shelves_resp.json().get("data", [])
    except Exception as e:
        print(f"Исключение при получении полок: {str(e)}")
        return None


def get_books_in_shelf(base_url, headers, shelf_id):
    """Получить список книг в полке."""
    try:
        books_resp = requests.get(f"{base_url}/api/shelves/{shelf_id}", headers=headers)
        if books_resp.status_code != 200:
            print(f"Ошибка получения книг полки {shelf_id}: {books_resp.text}")
            return None
        data = books_resp.json()
        return data.get("books", []) if data else []
    except Exception as e:
        print(f"Исключение при получении книг: {str(e)}")
        return None


def create_or_get_shelf(base_url, headers, shelf_name):
    """Получить существующую полку по имени или создать новую."""
    try:
        # Получить все полки
        shelves_resp = requests.get(f"{base_url}/api/shelves", headers=headers)
        if shelves_resp.status_code != 200:
            print(f"Ошибка доступа к полкам: {shelves_resp.text}")
            return None

        shelves = shelves_resp.json().get("data", [])
        shelf = next((s for s in shelves if s["name"] == shelf_name), None)
        if shelf:
            return shelf["id"]

        # Создать новую полку
        shelf_payload = {
            "name": shelf_name,
            "description": f"Конвертировано {datetime.now().strftime('%Y-%m-%d')}",
            "books": [],
        }
        create_resp = requests.post(
            f"{base_url}/api/shelves", headers=headers, json=shelf_payload
        )
        if create_resp.status_code != 200:
            print(f"Ошибка создания полки: {create_resp.text}")
            return None

        return create_resp.json()["id"]

    except Exception as e:
        print(f"Исключение при работе с полкой: {str(e)}")
        return None


def create_or_get_book_in_shelf(base_url, headers, shelf_id, book_name):
    """Получить существующую книгу в полке по имени или создать новую и добавить."""
    try:
        # Получить книги полки
        books = get_books_in_shelf(base_url, headers, shelf_id)
        if books is None:
            return None
        book = next((b for b in books if b["name"] == book_name), None)
        if book:
            return book["id"]

        # Создать новую книгу
        book_payload = {
            "name": book_name,
            "description": f"Конвертировано из DOCX ({datetime.now().strftime('%Y-%m-%d')})",
            "tags": [{"name": "конвертировано", "value": "docx2md"}],
        }
        book_resp = requests.post(
            f"{base_url}/api/books", headers=headers, json=book_payload
        )
        if book_resp.status_code not in [200, 201]:
            print(f"Ошибка создания книги '{book_name}': {book_resp.text}")
            return None

        book_data = book_resp.json()
        book_id = book_data["id"]

        # Добавить на полку
        add_payload = {"books": [book_id]}
        add_resp = requests.post(
            f"{base_url}/api/shelves/{shelf_id}/books",
            headers=headers,
            json=add_payload,
        )
        if add_resp.status_code != 200:
            print(f"Ошибка добавления книги на полку: {add_resp.text}")
            return None

        print(f"Книга '{book_name}' создана и добавлена (ID: {book_id})")
        return book_id

    except Exception as e:
        print(f"Исключение при работе с книгой: {str(e)}")
        return None


def create_page_from_md(base_url: str, headers: dict, book_id: int, md_path: str):
    """Создаёт страницу на сервере, передавая исходный Markdown в поле 'markdown'."""
    try:
        # Чтение markdown-файла
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        page_name = Path(md_path).stem

        payload = {
            "name": page_name,
            "book_id": book_id,
            "markdown": md_content,  # <-- отправляем markdown, не конвертируем в HTML
            "priority": 1,
            "draft": False,
            "tags": [{"name": "страница-из-md"}],
        }

        resp = requests.post(
            f"{base_url}/api/pages", headers=headers, json=payload, timeout=30
        )

        # Учитываем успешные коды 200..299 (включая 201)
        if resp.ok:
            try:
                return resp.json()
            except ValueError:
                # Если ответ не JSON — вернуть текст
                return resp.text
        else:
            print(
                f"Ошибка создания страницы '{page_name}': {resp.status_code} {resp.text}"
            )
            return False

    except (IOError, OSError) as e:
        print(f"Ошибка чтения файла '{md_path}': {e}")
        return False
    except requests.RequestException as e:
        print(f"Сетевая ошибка при запросе к {base_url}: {e}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка: {e}")
        return False

    except Exception as e:
        print(f"Исключение при создании страницы: {str(e)}")
        return False
