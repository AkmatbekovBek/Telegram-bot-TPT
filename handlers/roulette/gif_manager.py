# handlers/roulette/gif_manager.py
import os
import random
import asyncio
import logging
from typing import Optional
from aiogram import types
from aiogram.types import InputFile

logger = logging.getLogger(__name__)


class RouletteGIFManager:
    """Менеджер GIF-анимаций для рулетки с локальными файлами"""

    def __init__(self, base_path: str = "media"):
        self.base_path = base_path
        self.gif_files = self._find_gif_files()

    def _find_gif_files(self) -> list:
        """Найти все GIF файлы в директории"""
        gif_files = []

        if os.path.exists(self.base_path):
            for file in os.listdir(self.base_path):
                if file.lower().endswith('.gif'):
                    gif_files.append(os.path.join(self.base_path, file))

        # Если нет файлов, используем встроенные названия
        if not gif_files:
            # Проверяем существование конкретного файла
            default_gif = os.path.join(self.base_path, "rlt2.gif")
            if os.path.exists(default_gif):
                gif_files.append(default_gif)

        logger.info(f"Найдено GIF файлов: {len(gif_files)}")
        return gif_files

    def get_random_gif(self) -> Optional[InputFile]:
        """Получить случайный GIF файл"""
        if not self.gif_files:
            return None

        gif_path = random.choice(self.gif_files)
        if os.path.exists(gif_path):
            try:
                return InputFile(gif_path)
            except Exception as e:
                logger.error(f"Ошибка создания InputFile: {e}")
        return None

    async def send_spin_gif(self, bot, chat_id: int, caption: str = None) -> Optional[types.Message]:
        """Отправить GIF анимацию кручения рулетки"""
        try:
            gif_file = self.get_random_gif()

            if gif_file:
                # Отправляем GIF как анимацию
                msg = await bot.send_animation(
                    chat_id=chat_id,
                    animation=gif_file,
                    caption=caption or "🎰 *Рулетка крутится...*",
                    parse_mode="Markdown"
                )
                return msg
            else:
                # Fallback на текстовую анимацию
                return await self.send_text_animation(bot, chat_id, caption)

        except Exception as e:
            logger.error(f"Ошибка отправки GIF: {e}")
            return await self.send_text_animation(bot, chat_id, caption)

    @staticmethod
    async def send_text_animation(bot, chat_id: int, caption: str = None) -> Optional[types.Message]:
        """Текстовая анимация (fallback)"""
        try:
            # Кадры текстовой анимации
            frames = [
                "🎰 Рулетка крутится... 🔄",
                "🎰 Рулетка крутится... ⏳",
                "🎰 Рулетка крутится... 💫",
                "🎰 Рулетка крутится... ✨",
                "🎰 *СТОП!* Результат..."
            ]

            if caption:
                frames[-1] = caption

            msg = None
            for frame in frames:
                try:
                    if msg:
                        # Редактируем предыдущее сообщение
                        await msg.edit_text(frame, parse_mode="Markdown")
                    else:
                        # Создаем новое сообщение
                        msg = await bot.send_message(
                            chat_id=chat_id,
                            text=frame,
                            parse_mode="Markdown"
                        )
                    await asyncio.sleep(0.5)  # Пауза между кадрами
                except Exception as e:
                    logger.debug(f"Ошибка в текстовой анимации: {e}")

            return msg
        except Exception as e:
            logger.error(f"Ошибка текстовой анимации: {e}")
            return None

    @staticmethod
    async def send_dots_animation(bot, chat_id: int, duration: float = 2.0) -> Optional[types.Message]:
        """Анимация с точками (простая)"""
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                parse_mode="Markdown"
            )

            dots = ["", ".", "..", "...", "....", "....."]
            for i in range(int(duration * 2)):  # Меняем каждые 0.5 секунды
                try:
                    await msg.edit_text(f"🎰 Рулетка крутится{dots[i % len(dots)]}")
                    await asyncio.sleep(0.5)
                except:
                    break

            return msg
        except Exception as e:
            logger.error(f"Ошибка dots анимации: {e}")
            return None