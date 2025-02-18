import time
import ccxt
import pandas as pd
import os
import pytz
import threading
import subprocess
from config import TELEGRAM_TOKEN_2, TARGET_TIMEZONE, CRYPTO_PAIR, TIMEFRAME, DATA_FILE, LOG_FILE
from logger import logger
from data_handler import save_data, load_data
from telegram_bot import bot, send_message
from exchange_utils import fetch_candles, calculate_sma, calculate_atr, check_crossing
from order_manager import place_order, place_tp_sl, exchange

# Делает текущую директорию рабочей
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Глобальная переменная для ID чата
chat_id = None
last_cross_time = None  # Глобальная переменная для отслеживания последнего пересечения
last_entry_price = None  # Цена последнего пересечения вверх
atr_at_entry = None  # ATR на момент входа

# Основной процесс мониторинга
def monitor_crypto():

    global chat_id, last_cross_time, last_entry_price, atr_at_entry

    # Загружаем chat_id из config.py
    try:
        from config import CHAT_ID
        chat_id = CHAT_ID
        logger.info(f"✅ Загружен chat_id в test.py: {chat_id}")
    except ImportError:
        logger.error("⚠ Ошибка загрузки chat_id в test.py")

    # Загружаем исторические данные, если они есть
    df = load_data()
    logger.info("Загружаем исторические данные...")

    # Если данных недостаточно, запрашиваем новые свечи
    if df.empty or len(df) < 200:
        df = fetch_candles(CRYPTO_PAIR, TIMEFRAME)
        df = calculate_atr(df)
        save_data(df)  # Сохраняем данные

    logger.info("Бот запущен и мониторинг начат!")
    logger.info("Запускаем основной цикл мониторинга...")
    

    level_up_reached = False  # Флаг достижения +3ATR
    level_down_reached = False  # Флаг достижения -1ATR
    
    logger.info("🚀 Старт цикла мониторинга...")
    while True:
        try:
            # Получаем новые данные
            new_data = fetch_candles(CRYPTO_PAIR, TIMEFRAME)
            logger.info(f"Получены новые данные: {new_data.tail(1)}")

            # Обновляем DataFrame и сохраняем данные
            df = pd.concat([df, new_data]).drop_duplicates(subset="timestamp").reset_index(drop=True)
            df = calculate_atr(df)
            save_data(df)

            # Проверяем пересечения
            crossings = check_crossing(df)
            logger.info(f"Проверка пересечений, найдено: {len(crossings)}")

            if not crossings.empty:
                last_crossing = crossings.iloc[-1]
                cross_time = last_crossing["timestamp"]

                # Отправляем сообщение только при новом пересечении
                if last_cross_time != cross_time:
                    last_cross_time = cross_time

                    if last_crossing["SMA_50"] > last_crossing["SMA_200"]:  # Пересечение ВВЕРХ
                        direction = "Вверх"
                        last_entry_price = last_crossing["close"]  # Запоминаем цену пересечения
                        atr_at_entry = last_crossing["ATR"]  # Запоминаем ATR на момент входа

                        logger.info(f"🔥 Новое пересечение! last_entry_price: {last_entry_price}, atr_at_entry: {atr_at_entry}")
                        
                        # Выставляем ордер на покупку, TP, SL
                        try:
                            order = place_order(CRYPTO_PAIR, "buy", 10) 

                            if order:
                                try:
                                    entry_price = exchange.fetch_ticker(CRYPTO_PAIR)['last']  # Получаем текущую цену входа
                                    place_tp_sl(CRYPTO_PAIR, "buy", entry_price)
                                except Exception as e:
                                    logger.error(f"❌ Ошибка при получении цены входа: {e}", exc_info=True)

                        except Exception as e:
                            logger.error(f"❌ Ошибка при размещении ордера: {e}", exc_info=True)
                            order = None  # Чтобы код дальше выполнялся

                    else:
                        continue  # Пересечение вниз – ничего не делаем, пропускаем

                    current_price = last_crossing["close"]
                    #previous_price = last_crossing["close"] if len(crossings) < 2 else crossings.iloc[-2]["close"]

                    message = (
                        f"Пересечение обнаружено!\n"
                        f"Пара: {CRYPTO_PAIR}\n"
                        f"Направление: {direction}\n"
                        f"Время: {last_cross_time}\n"
                        #f"Прошлая цена: {previous_price}\n"
                        f"Текущая цена: {current_price}\n"
                        f"3ATR: {(last_entry_price + 10 * atr_at_entry):.4f}\n"
                        f"-1ATR: {(last_entry_price - 3 * atr_at_entry):.4f}"
                    )
                    send_message(message)
                    logger.info(f"Отправлено сообщение: {message}")

            if last_entry_price is not None and atr_at_entry is not None:
                level_up = last_entry_price + 10 * atr_at_entry  # Уровень 10ATR вверх
                level_down = last_entry_price - 3 * atr_at_entry   # Уровень -3ATR вниз
                current_price = df.iloc[-1]["close"]  # Текущая цена

                logger.info(f"📊 Проверка уровней: Текущая цена: {current_price}, 10ATR: {level_up}, -3ATR: {level_down}")

                if current_price >= level_up:
                    achievement_price = level_up  # Фиксируем цену достижения
                    achievement_time = df.iloc[-1]["timestamp"]  # Фиксируем время
                    logger.info(f"✅ Достигнут уровень +10ATR! Цена: {current_price}, уровень: {level_up}")
                    send_message(
                        f"Цена достигла +10ATR!\n"
                        f"Цена срабатывания: {achievement_price:.4f}\n"
                        f"Время: {achievement_time}"
                        )
                    last_entry_price = None  # Сбрасываем отслеживание
                    atr_at_entry = None

                elif current_price <= level_down:
                    achievement_price = level_down  # Фиксируем цену достижения
                    achievement_time = df.iloc[-1]["timestamp"]  # Фиксируем время
                    logger.info(f"❌ Достигнут уровень -3ATR! Цена: {current_price}, уровень: {level_down}")
                    send_message(
                        f"Цена достигла -3ATR!\n"
                        f"Цена срабатывания: {achievement_price:.4f}\n"
                        f"Время: {achievement_time}"
                        )
                    last_entry_price = None  # Сбрасываем отслеживание
                    atr_at_entry = None

            logger.info("Ожидание 30 секунд перед следующим циклом...")
            time.sleep(30)  # Проверяем каждые 30 секунд
        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            time.sleep(60)  # Пауза перед повторной попыткой


# Запуск бота
if __name__ == "__main__":
    import threading
    threading.Thread(target=monitor_crypto).start()

# Запускаем мониторинг криптовалюты в отдельном потоке
threading.Thread(target=monitor_crypto, daemon=True).start()

# Запускаем telegram_bot.py в отдельном процессе
logger.info("Запуск Telegram-бота...")
subprocess.Popen(["python", "telegram_bot.py"])

logger.info("Основной процесс test.py запущен.")