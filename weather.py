#!/usr/bin/env python3

import logging
import signal
import sys
import types

import requests


logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stdout
)
log = logging.getLogger(__name__)


def signal_handler(signum: int, frame: types.FrameType) -> None:
    """Handle Ctrl+C gracefully."""
    logging.info("\nПрерывание пользователем. Выход...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MAX_CITY_NAME_LENGTH = 100
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3

# https://www.nodc.noaa.gov/archive/arc0021/0002199/1.1/data/0-data/HTML/WMO-CODE/WMO4677.HTM
WEATHER_CODE_TO_DESCRIPTION_MAP = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "туман с изморозью",
    51: "слабый морось",
    53: "умеренная морось",
    55: "сильная морось",
    56: "слабый ледяной дождь",
    57: "сильный ледяной дождь",
    61: "небольшой дождь",
    63: "умеренный дождь",
    65: "сильный дождь",
    66: "слабый ледяной дождь",
    67: "сильный ледяной дождь",
    71: "небольшой снег",
    73: "умеренный снег",
    75: "сильный снег",
    77: "снежные зёрна",
    80: "небольшой ливень",
    81: "умеренный ливень",
    82: "сильный ливень",
    85: "небольшой снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с мелким градом",
    99: "гроза с крупным градом"
}


def sanitize_city_name(city_name: str) -> str:
    """
    Sanitize and validate city name input.
    """
    city_name = city_name.strip()

    if not city_name:
        raise ValueError("Название города не может быть пустым")

    if len(city_name) > MAX_CITY_NAME_LENGTH:
        raise ValueError(f"Название города не должно превышать {MAX_CITY_NAME_LENGTH} символов")

    dangerous_chars = [';', '|', '&', '$', '`', '>', '<', '\\', '"', "'"]
    for char in dangerous_chars:
        if char in city_name:
            raise ValueError(f"Название города содержит недопустимый символ: {char}")

    return city_name


def get_coordinates(city_name: str) -> tuple[float | None, float | None]:
    """
    Convert city name to latitude and longitude using Open-Meteo Geocoding API.
    """

    try:
        city_name = sanitize_city_name(city_name)
    except ValueError as e:
        log.error(f"Некорректное название города: {e}")
        return None, None

    log.debug(f"Запрос координат для города: {city_name}")

    params = {
        "name": city_name,
        "count": 1,
        "language": "ru",
        "format": "json"
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(GEOCODE_URL, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()

            if not data.get("results"):
                log.error(f"Город '{city_name}' не найден")
                return None, None

            location = data["results"][0]
            lat = location.get("latitude")
            lon = location.get("longitude")
            full_name = location.get("name", "")
            country = location.get("country", "")

            log.debug(f"Найден город: {full_name}, {country} (координаты: {lat}, {lon})")
            return lat, lon

        except requests.exceptions.Timeout:
            log.warning(f"Таймаут геокодинга, попытка {attempt + 1}/{MAX_RETRIES}")
            if attempt == MAX_RETRIES - 1:
                log.error("Превышено количество попыток геокодинга")
                return None, None

        except requests.exceptions.RequestException as e:
            log.error(f"Ошибка сети при геокодировании: {e}")
            return None, None
        except ValueError as e:
            log.error(f"Ошибка обработки ответа геокодинга: {e}")
            return None, None

    return None, None


def get_weather_by_coordinates(lat: float, lon: float) -> tuple[float | None, str | None]:
    """
    Get current weather by coordinates using Open-Meteo Forecast API.
    """
    if not (-90 <= lat <= 90):
        log.error(f"Некорректная широта: {lat}")
        return None, None

    if not (-180 <= lon <= 180):
        log.error(f"Некорректная долгота: {lon}")
        return None, None

    log.debug(f"Запрос погоды для координат: {lat}, {lon}")

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code",
        "temperature_unit": "celsius",
        "timezone": "auto",
        "forecast_days": 1
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(WEATHER_URL, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            weather_data = response.json()

            current = weather_data.get("current")
            if not current:
                log.error("Не удалось найти блок 'current' в ответе API")
                return None, None

            temp = current.get("temperature_2m")
            weather_code = current.get("weather_code")

            if weather_code is None:
                log.error("В ответе API отсутствует код погоды (weather_code)")
                return None, None

            description = WEATHER_CODE_TO_DESCRIPTION_MAP.get(weather_code, "неизвестно")

            log.debug(f"Погода получена: {temp:.1f}°C, {description} (код: {weather_code})")
            return temp, description

        except requests.exceptions.Timeout:
            log.warning(f"Таймаут погоды, попытка {attempt + 1}/{MAX_RETRIES}")
            if attempt == MAX_RETRIES - 1:
                log.error("Превышено количество попыток получения погоды")
                return None, None

        except requests.exceptions.RequestException as e:
            log.error(f"Ошибка сети при запросе погоды: {e}")
            return None, None
        except ValueError as e:
            log.error(f"Ошибка обработки ответа погоды: {e}")
            return None, None

    return None, None


def main() -> int:
    """
    Script entry point.
    """
    log.debug("Запуск скрипта погоды")

    if len(sys.argv) < 2:
        log.error(
            f"Неверное использование скрипта\n"
            f"Правильно: python {sys.argv[0]} <название_города>\n"
            f"Пример: python {sys.argv[0]} Москва"
        )
        return 1

    city_name = " ".join(sys.argv[1:])
    log.debug(f"Запрос погоды для города: {city_name}")

    lat, lon = get_coordinates(city_name)
    if lat is None or lon is None:
        log.error("Не удалось получить координаты города")
        return 1

    temp, description = get_weather_by_coordinates(lat, lon)
    if temp is None or description is None:
        log.error("Не удалось получить данные о погоде")
        return 1

    result_msg = (
        f"Город: {city_name}\n"
        f"Температура: {temp:.1f}°C\n"
        f"Описание: {description.capitalize()}"
    )

    log.info(result_msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
