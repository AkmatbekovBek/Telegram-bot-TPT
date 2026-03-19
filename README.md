# 🤖 Telegram-bot-TPT — Advanced Group Management & Gaming

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/aiogram-2.25.1-orange?style=for-the-badge&logo=telegram" />
  <img src="https://img.shields.io/badge/PostgreSQL-Enabled-336791?style=for-the-badge&logo=postgresql" />
  <img src="https://img.shields.io/badge/Architecture-Modular-success?style=for-the-badge" />
</p>

> **Telegram-bot-TPT** — многофункциональный бот для управления сообществами, включающий систему кланов, глубокую экономику и автоматизацию фоновых процессов.

---

## 🌟 Основной функционал

### 🏰 Система Кланов (Clan System)
* Создание, управление и вступление в кланы.
* Общий баланс клана, глобальный рейтинг (Top Clans) и автоматическое обновление очков.
* Система иерархии и клановых уведомлений.

### 💸 Экономика и Донаты
* Внутренняя валюта и система переводов между игроками.
* Проверка и валидация чеков пожертвований.
* Динамическая система статусов и бонусов.

### 🕒 Фоновые задачи (Background Tasks)
* Использование **APScheduler** для ежедневной очистки базы данных.
* Автоматическое снятие временных лимитов и ограничений пользователей.
* Постоянная проверка статусов оплаты в фоновом режиме.

### 🛡️ Модерация и Администрирование
* Система мутов и банов с временными интервалами.
* **Auto-ban Middleware** для предотвращения спама и флуда.
* Детальное логирование действий в файл `bot.log`.

---

## 🛠️ Технологический стек

| Компонент | Технология |
| :--- | :--- |
| **Язык** | `Python 3.11+` |
| **Фреймворк** | `Aiogram 2.25.1` |
| **База данных** | `PostgreSQL` / `SQLAlchemy 2.0` |
| **Миграции** | `Alembic` |
| **Планировщик** | `APScheduler` |

---

⚙️ Установка и запуск
Клонирование:

Bash
git clone [https://github.com/AkmatbekovBek/Telegram-bot-TPT.git](https://github.com/AkmatbekovBek/Telegram-bot-TPT.git)
cd Telegram-bot-TPT
Окружение:

Bash
python -m venv venv
source venv/bin/activate # Windows: venv\Scripts\activate
pip install -r requirements.txt
Настройка (.env):

Фрагмент кода
TGBOTtoken="ВАШ_ТОКЕН"
DATABASE_URL="postgresql://user:pass@localhost/dbname"

---

<p align="center">
  <img src="https://img.shields.io/badge/License-GNU%20GPL%20v3-red.svg?style=for-the-badge" />
</p>

---

<p align="center">
  <b>⚖️ License & Copyright / Лицензия и Авторское право</b><br>
  Copyright (c) 2024-2026 <b>Akmatbekov Bek</b>
</p>

<p align="center">
  <i>English Version:</i><br>
  This project is protected by the <b>GNU GPLv3</b> license.<br>
  Using the code is permitted <b>only with attribution</b> to the original author.<br>
  When modifying the code, a link to this repository is <b>mandatory</b>.
</p>

<p align="center">
  <i>Русская версия:</i><br>
  Данный проект защищен лицензией <b>GNU GPLv3</b>.<br>
  Использование кода разрешено <b>только с указанием авторства</b>.<br>
  При модификации кода ссылка на данный репозиторий <b>обязательна</b>.
</p>

---

<p align="center">
  <a href="https://t.me/твой_ник_в_тг">
    <img src="https://img.shields.io/badge/Contact_Author-Telegram-blue?style=flat-square&logo=telegram" />
  </a>
</p>

---

## 📂 Структура проекта

```bash
📦 Telegram-bot-TPT
 ┣ 📂 database/      # Модели SQLAlchemy и операции с БД
 ┣ 📂 handlers/      # Логика: кланы, донаты, игры (рулетка, слоты, воры)
 ┣ 📂 middlewares/   # Антиспам, авторегистрация и бан-система
 ┣ 📂 utils/         # Хелперы и настройка логирования
 ┣ 📜 main.py        # Точка запуска и регистрация систем
 ┗ 📜 const.py       # Текстовые шаблоны и константы
