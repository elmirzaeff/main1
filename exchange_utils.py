import ccxt
import pandas as pd
import pytz
from config import CRYPTO_PAIR, TIMEFRAME, TARGET_TIMEZONE
from logger import logger

# Подключение к бирже Bybit
exchange = ccxt.bybit({'enableRateLimit': True})

def fetch_candles(pair: str, timeframe: str) -> pd.DataFrame:
    """Получение свечных данных с биржи и их обработка."""
    try:
        logger.info(f"Запрашиваем данные {pair} на таймфрейме {timeframe}...")

        candles = exchange.fetch_ohlcv(pair, timeframe, limit=500)
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Преобразование времени в целевой часовой пояс
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        local_tz = pytz.timezone(TARGET_TIMEZONE)
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC").dt.tz_convert(local_tz).dt.tz_localize(None)

        logger.info(f"Успешно получены данные: {len(df)} свечей.")
        return df
    except Exception as e:
        logger.error(f"Ошибка при запросе данных с биржи {pair}: {e}", exc_info=True)
        return pd.DataFrame()


def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """Расчет скользящей средней."""
    return df["close"].rolling(window=period).mean()


def calculate_atr(df: pd.DataFrame, period: int = 50) -> pd.DataFrame:
    """Расчет ATR (Average True Range)."""
    df["high_low"] = df["high"] - df["low"]
    df["high_close"] = (df["high"] - df["close"].shift()).abs()
    df["low_close"] = (df["low"] - df["close"].shift()).abs()
    df["true_range"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
    df["ATR"] = df["true_range"].rolling(window=period).mean()
    return df


def check_crossing(df: pd.DataFrame) -> pd.DataFrame:
    """Проверка пересечения SMA-50 и SMA-200."""
    df["SMA_50"] = calculate_sma(df, 50)
    df["SMA_200"] = calculate_sma(df, 200)

    # Проверяем пересечения
    df["cross"] = (df["SMA_50"] > df["SMA_200"]).astype(int)
    df["cross_shift"] = df["cross"].shift(1)
    crossings = df[(df["cross"] != df["cross_shift"]) & (df["cross_shift"].notnull())]

    return crossings
