"""
Улучшенный менеджер текстов для доната с централизованным хранением.
"""

import json
import os
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Файл для хранения текстов
TEXTS_FILE = "donate_texts.json"

# ГЛАВНЫЕ ТЕКСТЫ - ТОЛЬКО ЗДЕСЬ МЕНЯЕМ
MAIN_TEXTS = {
    "main": """💎 Донат магазин @TopTashPlusBot

💰 Покупка монет:
▫️ 250.000 — 100₽
▫️ 600.000 — 200₽
▫️ 1.300.000 — 400₽
▫️ 2.800.000 — 700₽
▫️ 6.000.000 — 1.200₽
▫️ 14.000.000 — 2.000₽
▫️ 28.000.000 — 3.500₽
▫️ 60.000.000 — 6.000₽
▫️ 110.000.000 — 7.500₽

⸻

🎖️ Покупка статусов:
🌑 Бронза — 1000₽
• Ежедневный бонус: 500.000 монет
• Срок действия: 30 дней

💰 Платина — 2500₽
• Ежедневный бонус: 1.500.000 монет
• Срок действия: 30 дней

🥇 Золото — 5000₽
• Ежедневный бонус: 4.500.000 монет
• Срок действия: 30 дней

💎 Бриллиант — 8000₽
• Ежедневный бонус: 10.000.000 монет
• Срок действия: 30 дней

⸻

🏦 Реквизиты для оплаты:

🇷🇺 VTB BANK
2200 2480 0411 8401

🇰🇬 Balance (MegaCom)
+996 550 070 610

🇰🇬VISA MBANK
4177 4901 8146 7061 
(Bekmamat.E)

🇰🇬 VISA (O Bank!)
4196720053350145

🇰🇬 VISA (BAKAI BANK):
4714240010032374 (Bekmamat.E)

🇰🇿 (Kaspi Bank)
4400430297822295
(Азиза С.)

🇰🇿 (HALYK BANK)
4405 6397 2749 2199
(Азиза С.)

🇺🇿 UZ VISA
4916 9903 1199 4492 (Komilov S.)

🪙 USDT TRC20
TNkUXgFKLt88F83zqUxVroigQnHJio5Hco

⸻

📌 Как купить:
1. Выберите что хотите купить
2. Оплатите по реквизитам выше
3. Нажмите /чек и отправьте скриншот оплаты
4. В комментарии укажите что покупаете
5. Администратор проверит и начислит покупку

⸻

💎 Выберите действие:""",

    # Базовые тексты с динамической вставкой
    "buy_coins": """🛒 <b>Покупка монет</b>

{main_text_section}

📌 <b>Инструкция:</b>
1. Оплатите по реквизитам выше
2. Нажмите /чек и отправьте скриншот оплаты
3. В комментарии укажите "Покупка [количество] монет"
4. Администратор проверит и начислит монеты

🔎 <b>Пример:</b> "Покупка 1.300.000 монет" """,

    "statuses": """🎖️ <b>Покупка статусов</b>

{status_text_section}

📌 <b>Инструкция:</b>
1. Оплатите статус по реквизитам выше
2. Нажмите /чек и отправьте скриншот оплаты
3. В комментарии укажите "Покупка статуса [название]"
4. Администратор активирует статус

🔎 <b>Пример:</b> "Покупка статуса Бронза" """,

    "status_info": """🎖️ <b>{status_icon} {status_name}</b>

💰 <b>Цена:</b> {price_rub}₽
🎁 <b>Ежедневный бонус:</b> {bonus_amount:,} монет
⏰ <b>Срок действия:</b> {duration} дней

⸻

{requisites_section}

📌 <b>Как купить:</b>
1. Оплатите {price_rub}₽ по реквизитам выше
2. Нажмите /чек и отправьте скриншот оплаты
3. В комментарии укажите "Покупка статуса {status_name}"
4. Администратор активирует статус

⸻

👤 <b>Ваш ID для чека:</b> <code>{user_id}</code>
📝 Не забудьте указать ID в комментарии к оплате!""",

    "bonus": """🎁 <b>Бонусная система</b>

💰 <b>Ежедневный бонус:</b> зависит от вашего статуса

⏰ <b>Обновление:</b> каждые 24 часа

📊 <b>Бонусы по статусам:</b>
👤 Обычный — 100.000 монет
🌑 Бронза — 500.000 монет
💰 Платина — 1.500.000 монет
🥇 Золото — 4.500.000 монет
💎 Бриллиант — 10.000.000 монет""",

    "daily_bonus": """🎁 <b>Ежедневный бонус</b>

💰 <b>Ваш статус:</b> {status_name} {status_icon}
🎁 <b>Бонус:</b> {bonus_amount:,} монет/день
⏰ <b>Обновление:</b> каждые 24 часа
🕐 <b>Следующий бонус:</b> {next_bonus_time}""",

    "bonus_claimed": """🎉 <b>Бонус получен!</b>

💰 <b>Сумма:</b> {bonus_amount:,} монет
🎖️ <b>Статус:</b> {status_name}

⏰ <b>Следующий бонус через:</b> 24 часа""",

    "user_status_info": """📊 <b>Информация о вашем статусе</b>

🎖️ <b>Статус:</b> {status_icon} {status_name}
💰 <b>Ежедневный бонус:</b> {bonus_amount:,} монет
⏰ <b>Срок действия:</b> {days_left} дней
🕐 <b>Следующий бонус:</b> {next_bonus_time}

📈 <b>Статистика:</b>
🎁 <b>Всего бонусов:</b> можно получить сейчас
💸 <b>Общая сумма:</b> зависит от вашего статуса

💡 <b>Хотите больше?</b>
Приобретите более высокий статус для увеличения бонусов!

ℹ️ <b>Для покупки статуса:</b>
1. /донат → 👑 Статусы
2. Выберите нужный статус
3. Оплатите по реквизитам
4. Отправьте чек через /чек""",

    "error_text": """ <b>Произошла ошибка!</b>

Пожалуйста, попробуйте позже или используйте команду /чек для отправки чека.

💳 <b>Если проблема с оплатой:</b>
1. Проверьте правильность реквизитов
2. Убедитесь что отправили чек
3. Если проблема осталась — обратитесь к администратору""",

    "bonus_available": "🎉 <b>Статус:</b> бонус доступен!\nНажмите кнопку получения в меню бонусов",

    "bonus_cooldown": "⏳ <b>Статус:</b> до следующего бонуса {time_left}",

    "check_instructions": """📸 <b>Отправка чека об оплате</b>

ℹ️ <b>Инструкция:</b>
1. Сделайте скриншот успешной оплаты
2. Отправьте фото или скриншот в этот чат
3. В комментарии укажите что покупаете

📝 <b>Примеры комментариев:</b>
• "Покупка 1.300.000 монет"
• "Покупка статуса Бронза"
• "Покупка статуса Платина"

⏳ <b>Время обработки:</b> до 24 часов
👨‍💼 <b>Кто проверяет:</b> администратор

⚠️ <b>Внимание:</b>
• Отправляйте только реальные чеки
• Фальшивые чеки приведут к бану
• Чек должен быть читаемым

🆔 <b>Ваш ID:</b> <code>{user_id}</code>
Не забудьте указать ID при оплате!"""
}

# Вспомогательные функции для разбивки главного текста
def _extract_main_section() -> str:
    """Извлекает секцию покупки монет из главного текста"""
    lines = MAIN_TEXTS["main"].split('\n')
    result = []
    collecting = False

    for line in lines:
        if "Покупка монет:" in line or collecting:
            result.append(line)
            collecting = True
            if "⸻" in line and len(result) > 5:  # Заканчиваем после первого разделителя
                break

    # Убираем лишние разделители
    while result and result[-1].strip() == "⸻":
        result.pop()

    return '\n'.join(result)

def _extract_status_section() -> str:
    """Извлекает секцию покупки статусов из главного текста"""
    lines = MAIN_TEXTS["main"].split('\n')
    result = []
    collecting = False
    status_found = False

    for i, line in enumerate(lines):
        if "Покупка статусов:" in line:
            collecting = True
            result.append(line)
        elif collecting:
            result.append(line)
            if "⸻" in line and status_found:
                # Проверяем, если следующий разделитель близко
                if i + 1 < len(lines) and "⸻" in lines[i + 1]:
                    break

    # Убираем лишние разделители в конце
    while result and result[-1].strip() == "⸻":
        result.pop()

    return '\n'.join(result)

def _extract_requisites_section() -> str:
    """Извлекает секцию реквизитов из главного текста"""
    lines = MAIN_TEXTS["main"].split('\n')
    result = []
    collecting = False

    for i, line in enumerate(lines):
        if "Реквизиты для оплаты:" in line:
            collecting = True
            result.append(line)
        elif collecting:
            result.append(line)
            # Заканчиваем перед "Как купить:"
            if "Как купить:" in line:
                result.pop()  # Убираем эту строку
                break

    return '\n'.join(result)

class DonateTextsSimple:
    """Улучшенный менеджер текстов для доната"""

    def __init__(self):
        self.texts = self._load_texts()
        self._preprocess_texts()
        logger.info(f"✅ Загружено {len(self.texts)} текстов доната")

    def _load_texts(self) -> Dict:
        """Загружает тексты из файла или создает дефолтные"""
        try:
            if os.path.exists(TEXTS_FILE):
                with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
                    texts = json.load(f)
                    # Объединяем с главными текстами
                    for key, value in MAIN_TEXTS.items():
                        if key not in texts:
                            texts[key] = value
                    return texts
        except Exception as e:
            logger.error(f" Ошибка загрузки текстов: {e}")

        # Возвращаем главные тексты
        return MAIN_TEXTS.copy()

    def _preprocess_texts(self):
        """Предобрабатывает тексты, заменяя плейсхолдеры"""
        # Извлекаем секции из главного текста
        main_section = _extract_main_section()
        status_section = _extract_status_section()
        requisites_section = _extract_requisites_section()

        # Заменяем плейсхолдеры
        for key in self.texts:
            if key == "buy_coins":
                self.texts[key] = self.texts[key].format(main_text_section=main_section)
            elif key == "statuses":
                self.texts[key] = self.texts[key].format(status_text_section=status_section)
            elif key == "status_info":
                # Этот форматируется динамически при вызове
                pass

    def _save_texts(self):
        """Сохраняет тексты в файл"""
        try:
            with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.texts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f" Ошибка сохранения текстов: {e}")
            return False

    def get(self, key: str, **kwargs) -> str:
        """Получает текст по ключу с возможностью форматирования"""
        # Автоматическое исправление ключа для обратной совместимости
        if key == "coins":
            logger.debug(f"Заменяем устаревший ключ 'coins' на 'buy_coins'")
            key = "buy_coins"

        text = self.texts.get(key)
        if text is None:
            return f" Текст '{key}' не найден"

        # Динамическое форматирование
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError as e:
                logger.error(f" Ошибка форматирования текста '{key}': {e}")
                return text
        return text

    def set(self, key: str, text: str) -> bool:
        """Устанавливает новый текст"""
        # Автоматическое исправление ключа для обратной совместимости
        if key == "coins":
            logger.info(f"⚠️ Заменяем ключ 'coins' на 'buy_coins' при сохранении")
            key = "buy_coins"

        self.texts[key] = text
        return self._save_texts()

    def update_main_text(self, new_text: str) -> bool:
        """Обновляет главный текст и пересчитывает все зависимые тексты"""
        self.texts["main"] = new_text
        self._preprocess_texts()
        return self._save_texts()

    def get_main_text(self) -> str:
        """Возвращает главный текст"""
        return self.texts.get("main", "")

    def list_all(self) -> Dict:
        """Возвращает все тексты"""
        return self.texts.copy()

    def reset(self, key: str) -> bool:
        """Сбрасывает текст к дефолтному"""
        if key in MAIN_TEXTS:
            self.texts[key] = MAIN_TEXTS[key]
            self._preprocess_texts()
            return self._save_texts()
        return False

    def reset_all(self) -> bool:
        """Сбрасывает все тексты к дефолтным"""
        for key in MAIN_TEXTS:
            self.texts[key] = MAIN_TEXTS[key]
            self._preprocess_texts()
            return self._save_texts()


# Глобальный экземпляр
donate_texts = DonateTextsSimple()


# Функции для удобного доступа
def get_donate_text(key: str, **kwargs) -> str:
    """Быстрый доступ к тексту"""
    return donate_texts.get(key, **kwargs)

def update_main_text(new_text: str) -> bool:
    """Обновляет главный текст"""
    return donate_texts.update_main_text(new_text)

def get_main_text() -> str:
    """Получает главный текст"""
    return donate_texts.get_main_text()