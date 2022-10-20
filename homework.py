import logging
import sys
import os

import requests
import time

import telegram

from dotenv import load_dotenv
from http import HTTPStatus

from exceptions import (
    ResponseDictEmptyError,
    HomeworksNotInResponseError,
    HomeworksListEmptyError,
    HomeworksNotListError,
    HomeworkStatusError,
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


HOMEWORK_STATUSES = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {"from_date": timestamp}
    homework_statuses = requests.get(ENDPOINT, headers=HEADERS, params=params)

    if homework_statuses.status_code != HTTPStatus.OK:
        raise StatusCodeError("Статус кода отличается от 200.")

    return homework_statuses.json()


def check_response(response):
    """Проверка ответа API на корректность."""
    if not isinstance(response, dict):
        raise TypeError("Ответ приходит не в виде словаря.")

    if not response:
        raise ResponseDictEmptyError("Словарь пустой!")

    if "homeworks" not in response:
        raise HomeworksNotInResponseError('Ключа "homeworks" нет в словаре.')

    if not isinstance(response["homeworks"], list):
        raise HomeworksNotListError("Homeworks не является списком.")

    return response["homeworks"]


def parse_status(homework):
    """Извлечение из информации о конкретной.
    домашней работе статус этой работы.
    """
    if "homework_name" not in homework:
        raise KeyError("У домашней работы нет имени.")

    if "status" not in homework:
        raise HomeworkStatusError("У домашней работы нет статуса.")

    homework_name = homework["homework_name"]
    homework_status = homework["status"]

    if homework_status not in HOMEWORK_STATUSES:
        raise StatusError("Недокументированный статус домашней работы.")

    verdict = HOMEWORK_STATUSES[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

    for token in tokens:
        if token is None:
            return False

    return True


def main():
    """Основная логика работы бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

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
            else:
                raise HomeworksListEmptyError("Список Homeworks пустой.")

            current_timestamp = response["current_date"]

        except (HomeworksNotInResponseError,
                HomeworksNotListError,
                HomeworkStatusError,
                StatusError,
                StatusCodeError,) as error:
            logging.error(error)
            message_error = f"Сбой в работе программы: {error}"

        except HomeworksListEmptyError:
            logging.debug("Статус домашней работы не обновился.")

        except Exception as error:
            logging.error(error)
            message_error = f"Сбой в работе программы: {error}"

        finally:
            if message != message_before:
                send_message(bot, message)
                logging.info("Сообщение отправлено")
                message_before = message

            if message_error != message_error_before:
                send_message(bot, message_error)
                logging.info("Сообщение отправлено")
                message_error_before = message_error

            time.sleep(RETRY_TIME)


if __name__ == "__main__":
    main()
