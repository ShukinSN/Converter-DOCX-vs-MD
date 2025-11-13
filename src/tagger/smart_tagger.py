import re
import yaml
from pathlib import Path
from typing import List, Dict, Set
import logging
import sys


class SmartTagger:
    def __init__(self, config_path: str = None):
        if config_path is None:
            base = Path(
                getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent)
            )
            config_path = base / "src" / "config" / "tags_mapping.yaml"
        self.config = self._load_config(config_path)

    def _load_config(self, path: str) -> Dict:
        default = {
            "document_types": {
                "руководство_программиста": [
                    "программиста",
                    "programmer",
                    "разработка",
                ],
                "руководство_оператора": ["оператора", "operator", "эксплуатация"],
                "руководство_пользователя": ["пользователя", "user", "руководство"],
                "руководство_куратора": ["куратора", "curator", "ИБ"],
                "описание_ПО": ["описание", "software", "ПО", "программное"],
                "описание_алгоритма": ["алгоритма", "algorithm", "логика"],
            },
            "systems": {
                "АРМ_оператора": ["АРМ", "оператора", "рабочее", "место"],
                "контроллер_ТН-01": [
                    "ТН-01",
                    "измерительно-вычислительный",
                    "контроллер",
                ],
                "контроллер_управления": ["контроллер", "управления", "control"],
                "СОИ_СИКН": ["СОИ", "СИКН", "система", "информации"],
            },
            "components": {
                "программное_обеспечение": ["ПО", "программное", "software"],
                "алгоритмы": ["алгоритм", "algorithm", "логика"],
                "интерфейс": ["интерфейс", "interface", "пользовательский"],
                "безопасность": ["ИБ", "безопасность", "security"],
            },
        }
        try:
            p = Path(path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    user = yaml.safe_load(f) or {}
                return self._merge(default, user)
        except Exception as e:
            logging.warning(f"Config load error: {e}")
        return default

    def _merge(self, default: Dict, user: Dict) -> Dict:
        res = default.copy()
        for cat, vals in user.items():
            if cat in res:
                res[cat].update(vals)
            else:
                res[cat] = vals
        return res

    def _title_tags(self, title: str) -> Set[str]:
        tags = set()
        low = title.lower()
        if any(w in low for w in ["программиста", "programmer"]):
            tags.update(
                ["руководство_программиста", "программист", "программная_документация"]
            )
        if any(w in low for w in ["оператора", "operator"]):
            tags.update(
                ["руководство_оператора", "оператор", "эксплуатационная_документация"]
            )
        if any(w in low for w in ["пользователя", "user"]):
            tags.update(
                [
                    "руководство_пользователя",
                    "пользователь",
                    "эксплуатационная_документация",
                ]
            )
        if any(w in low for w in ["куратора", "curator", "ИБ"]):
            tags.update(["руководство_куратора", "куратор", "безопасность"])
        if any(w in low for w in ["описание", "description"]):
            if "программного" in low or "ПО" in low:
                tags.update(["описание_ПО", "программное_обеспечение"])
            if "алгоритма" in low:
                tags.update(["описание_алгоритма", "алгоритмы"])
        if "АРМ" in title or "рабочее место" in low:
            tags.update(["АРМ_оператора", "интерфейс"])
        if "ТН-01" in title:
            tags.update(["контроллер_ТН-01", "измерительная_система"])
        if "контроллер управления" in low:
            tags.update(["контроллер_управления", "управление"])
        if "СОИ" in title or "СИКН" in title:
            tags.update(["СОИ_СИКН", "система_информации"])
        return tags

    def _content_tags(self, text: str) -> Set[str]:
        tags = set()
        sample = text[:3000].lower()
        for cat, items in self.config.items():
            for tag, pats in items.items():
                for p in pats:
                    if p.lower() in sample:
                        tags.add(tag)
                        break
        return tags

    def get_document_tags(self, file_path: Path, content: str = None) -> List[str]:
        tags = self._title_tags(file_path.stem)
        if content:
            tags.update(self._content_tags(content))
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    tags.update(self._content_tags(f.read()))
            except:
                pass
        tags.update(["автосгенерировано", "ЦПА", "техническая_документация"])
        return sorted(tags)

    def predict_tags_for_book(self, book_title: str) -> List[str]:
        return sorted(self._title_tags(book_title))
