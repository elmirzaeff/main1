import telebot
from config import TELEGRAM_TOKEN_2, CRYPTO_PAIR, TIMEFRAME, DATA_FILE, TARGET_TIMEZONE, LOG_FILE
from logger import logger
from data_handler import load_data
import time
import re

bot = telebot.TeleBot(TELEGRAM_TOKEN_2)
chat_id = None  # Глобальная переменная для хранения ID чата

last_cross_time = None
last_entry_price = None
atr_at_entry = None

def update_chat_id(chat_id):
    config_path = "config.py"

    try:
        # Читаем текущий файл
        with open(config_path, "r", encoding="utf-8") as file:
            config_content = file.readlines()

        # Ищем строку с CHAT_ID и обновляем её
        new_content = []
        chat_id_found = False
        for line in config_content:
            if line.startswith("CHAT_ID ="):
                new_content.append(f"CHAT_ID = {chat_id}\n")
                chat_id_found = True
            else:
                new_content.append(line)

        # Если строки с CHAT_ID не было, добавляем её в конец файла
        if not chat_id_found:
            new_content.append(f"CHAT_ID = {chat_id}\n")

        # Записываем изменения обратно
        with open(config_path, "w", encoding="utf-8") as file:
            file.writelines(new_content)

        print(f"✅ chat_id ({chat_id}) успешно обновлен в config.py")

    except Exception as e:
        print(f"❌ Ошибка при обновлении chat_id: {e}")

def send_message(message):
    """Отправка сообщений пользователю с логированием ошибок."""
    global chat_id

    # Загружаем chat_id из config.py, если он не установлен
    if chat_id is None:
        try:
            from config import CHAT_ID
            chat_id = CHAT_ID
            logger.info(f"✅ Загружен chat_id из config.py: {chat_id}")
        except ImportError:
            logger.error("⚠ Ошибка импорта CHAT_ID из config.py")

    logger.info(f"📨 Попытка отправить сообщение в Telegram: {message}")
    
    if chat_id:
        try:
            bot.send_message(chat_id, message)
            logger.info(f"✅ Сообщение отправлено в Telegram: {message}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в Telegram: {e}", exc_info=True)
    else:
        logger.warning("⚠ ID чата не задан, сообщение не отправлено.")

@bot.message_handler(commands=['start'])
def start_message(message):
    global chat_id
    chat_id = message.chat.id
    logger.info(f"✅ Получена команда /start от пользователя {chat_id}")

    # Обновляем chat_id в config.py
    update_chat_id(chat_id)

    bot.send_message(chat_id, f"Мониторинг {CRYPTO_PAIR} на {TIMEFRAME} таймфрейме начат!")
    logger.info("📨 Сообщение подтверждения отправлено в Telegram.")

        # Проверяем, установлен ли chat_id
    logger.info(f"📌 Проверка: chat_id теперь = {chat_id}")

@bot.message_handler(commands=['status'])
def status_message(message):
    """Отправляет статус мониторинга пользователю."""
    global chat_id
    if chat_id is None:
        chat_id = message.chat.id  # Запоминаем chat_id, если его ещё нет

    df = load_data()
    if df.empty:
        bot.send_message(chat_id, "Данные ещё не загружены, подождите...")
        return

    try:
        current_price = df.iloc[-1]["close"]
        last_cross = "Нет пересечений"
        last_entry = "Нет активных входов"

        if last_cross_time:
            last_cross = f"{last_cross_time} (SMA-50 {'выше' if last_entry_price else 'ниже'} SMA-200)"

        if last_entry_price is not None and atr_at_entry is not None:
            level_up = last_entry_price + 3 * atr_at_entry
            level_down = last_entry_price - 1 * atr_at_entry
            last_entry = (
                f"Цена входа: {last_entry_price:.4f}\n"
                f"3ATR: {level_up:.4f}\n"
                f"-1ATR: {level_down:.4f}"
            )

        message_text = (
            f"📊 *Статус мониторинга:*\n"
            f"Пара: {CRYPTO_PAIR}\n"
            f"Текущая цена: {current_price:.4f}\n"
            f"Последнее пересечение: {last_cross}\n"
            f"{last_entry}"
        )

        bot.send_message(chat_id, message_text, parse_mode="Markdown")
        logger.info("Отправлен статус мониторинга.")
    except Exception as e:
        logger.error(f"Ошибка при отправке статуса: {e}", exc_info=True)
        bot.send_message(chat_id, "Ошибка при получении статуса. Проверьте логи.")

@bot.message_handler(commands=['help'])
def help_message(message):
    """Отправляет список доступных команд."""
    help_text = (
        "📌 *Доступные команды:*\n"
        "/start - Запуск мониторинга\n"
        "/status - Проверить текущий статус\n"
        "/help - Список доступных команд\n"
        "/config - Текущие настройки бота\n"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")
    logger.info("Отправлено сообщение с командами /help")

@bot.message_handler(commands=['config'])
def config_message(message):
    """Отправляет текущие настройки бота пользователю."""
    config_text = (
        "⚙ *Текущие настройки бота:*\n"
        f"📌 Пара: `{CRYPTO_PAIR}`\n"
        f"🕒 Таймфрейм: `{TIMEFRAME}`\n"
        f"📂 Файл данных: `{DATA_FILE}`\n"
        f"🌍 Часовой пояс: `{TARGET_TIMEZONE}`\n"
        f"📝 Файл логов: `{LOG_FILE}`"
    )
    bot.send_message(message.chat.id, config_text, parse_mode="Markdown")
    logger.info("Отправлено сообщение с конфигурацией /config")

if __name__ == "__main__":
    while True:
        try:
            logger.info("Запуск bot.polling()...")
            bot.polling(non_stop=True, interval=0.5, timeout=20)
        except Exception as e:
            logger.error(f"Ошибка в bot.polling(): {e}", exc_info=True)
            time.sleep(15)  # Ждём 15 секунд перед повторным запуском