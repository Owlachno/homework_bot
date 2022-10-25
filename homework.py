import logging
import sys
import os
import requests
import time
from http import HTTPStatus

import telegram
from dotenv import load_dotenv

from exceptions import (
    StatusError,
    StatusCodeError,
    TokensError,
)

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_TIME = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}


HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception:
        logging.error("Не получилось отправить "
                      f"сообщение в чат: {TELEGRAM_CHAT_ID}.")
    else:
        logging.info(f"Сообщение отправлено чат: {TELEGRAM_CHAT_ID}")


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    params = {"from_date": current_timestamp}
    homework_statuses = requests.get(ENDPOINT, headers=HEADERS, params=params)

    if homework_statuses.status_code != HTTPStatus.OK:
        raise StatusCodeError(
            "Статус кода отличается от 200.",
            f"Пришедший статус: {homework_statuses.status_code}.",
            f"Адрес: {ENDPOINT}. Заголовки: {HEADERS}."
        )

    try:
        homework_statuses.json()
    except ValueError as error:
        logging.error(f"Ошибка: {error}. Ответ пришел не в формате json.")

    return homework_statuses.json()


def check_response(response):
    """Проверка ответа API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(
            "Ответ пришел не в виде словаря.",
            f"Тип пришедшего объекта: {type(response)}"
        )

    if "homeworks" not in response:
        raise KeyError('Ключа "homeworks" нет в словаре.')

    homeworks = response["homeworks"]

    if not isinstance(homeworks, list):
        raise TypeError(
            "Homeworks не является списком.",
            f"Тип объекта:{homeworks}"
        )

    return homeworks


def parse_status(homework):
    """Извлечение из информации о конкретной.
    домашней работе статус этой работы.
    """
    if "homework_name" not in homework:
        raise KeyError("У домашней работы нет имени.")

    if "status" not in homework:
        raise KeyError("У домашней работы нет статуса.")

    homework_name = homework["homework_name"]
    homework_status = homework["status"]

    if homework_status not in HOMEWORK_VERDICTS:
        raise StatusError("Недокументированный статус домашней работы.")

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    tokens = [
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    ]

    for name, value in tokens:
        if value is None:
            logging.error(f"Токен {name} недоступен!")
            return False

    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise TokensError("Ошибка в токенах!!")

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    message_before = None
    message_error_before = None
    message = None
    message_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)

            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])

            if 'current_date' not in response:
                current_timestamp = int(time.time())
                raise KeyError("В словаре нет даты.")

            else:
                current_timestamp = response['current_date']

        except Exception as error:
            logging.error(error)
            message_error = f"Сбой в работе программы: {error}"

        finally:
            if message != message_before:
                send_message(bot, message)
                message_before = message

            else:
                logging.debug("Статус домашней работы не обновился.")

            if message_error != message_error_before:
                send_message(bot, message_error)
                message_error_before = message_error

            time.sleep(RETRY_TIME)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format=("%(asctime)s - [%(levelname)s] "
                "- %(funcName)s(%(lineno)d) - %(message)s"),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(filename='hwbot_log.log'),
        ],
    )

    main()
