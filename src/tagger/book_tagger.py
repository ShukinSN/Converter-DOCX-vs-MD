import requests
from .smart_tagger import SmartTagger


class BookStackBookTagger:
    def __init__(self, base_url: str, token_id: str, token_secret: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Token {token_id}:{token_secret}",
            "Content-Type": "application/json",
        }
        self.tagger = SmartTagger()

    def get_books(self):
        try:
            r = requests.get(
                f"{self.base_url}/api/books", headers=self.headers, timeout=10
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except:
            return []

    def tag_book(self, book_id: int, book_name: str, log_callback=None):
        tags = self.tagger.predict_tags_for_book(book_name)
        if not tags:
            if log_callback:
                log_callback(f"Нет тегов для: {book_name}", "orange")
            return False

        payload = {"tags": [{"name": t, "value": ""} for t in tags]}
        try:
            resp = requests.put(
                f"{self.base_url}/api/books/{book_id}",
                headers=self.headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                if log_callback:
                    log_callback(f"Тегировано: {book_name}", "green")
                return True
        except Exception as e:
            if log_callback:
                log_callback(f"Ошибка: {e}", "red")
        return False
