"""
Простой менеджер текстов для ссылок.
"""

import json
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Файл для хранения текстов
LINKS_FILE = "links_text.json"

# Текст по умолчанию
DEFAULT_LINKS_TEXT = """
🔥 Все новости и обновления бота здесь:
👉 @newsTPT

🇰🇬 Чат для игроков из Кыргызстана:
👉 @kgz_TPT

🇰🇿 Чат для игроков из Казахстана:
👉 @kz_TPT

🇺🇿 Чат для игроков из Узбекистана:
👉 @uz_TPT

💎 VIP-чат владельца:
👉 @vipAnonymouss

🏆 Турнирный чат — соревнуйтесь, выигрывайте ценные призы и монеты:
👉 @tournamentTPT

🎁 Чат розыгрышей — шанс бесплатно выиграть ценные призы:
👉 @freecoin_TPT
"""


class LinkTextsSimple:
    """Простой менеджер текстов для ссылок"""

    def __init__(self):
        self.text = self._load_text()
        logger.info(f"✅ Загружен текст ссылок ({len(self.text)} символов)")

    def _load_text(self) -> str:
        """Загружает текст из файла или создает дефолтный"""
        try:
            if os.path.exists(LINKS_FILE):
                with open(LINKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("links_text", DEFAULT_LINKS_TEXT)
        except Exception as e:
            logger.error(f" Ошибка загрузки текста ссылок: {e}")

        # Возвращаем дефолтный текст
        return DEFAULT_LINKS_TEXT

    def _save_text(self):
        """Сохраняет текст в файл"""
        try:
            with open(LINKS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"links_text": self.text}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f" Ошибка сохранения текста ссылок: {e}")
            return False

    def get(self) -> str:
        """Получает текст ссылок"""
        return self.text

    def set(self, text: str) -> bool:
        """Устанавливает новый текст"""
        self.text = text
        return self._save_text()

    def reset(self) -> bool:
        """Сбрасывает текст к дефолтному"""
        self.text = DEFAULT_LINKS_TEXT
        return self._save_text()


# Глобальный экземпляр
link_texts = LinkTextsSimple()