import datetime
import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import StatusCodeError, TokensError

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_TIME = 500
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
    except Exception as error:
        logging.error(f"Ошибка: {error}. Не получилось отправить "
                      f"сообщение в чат: {TELEGRAM_CHAT_ID}.")
    else:
        logging.info(f"Сообщение отправлено чат: {TELEGRAM_CHAT_ID}")


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    params = {"from_date": current_timestamp}

    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params)
    except Exception as error:
        raise Exception(
            f"Ошибка в GET-запросе к API сервиса Яндекс.Практикум: {error}. "
            f"Адрес: {ENDPOINT}. Заголовки: {HEADERS}. "
            f"Параметры: {params}."
        )

    if homework_statuses.status_code != HTTPStatus.OK:
        raise StatusCodeError(
            "Статус кода отличается от 200. "
            f"Пришедший статус: {homework_statuses.status_code}. "
            f"Адрес: {ENDPOINT}. Заголовки: {HEADERS}. "
            f"Параметры: {params}."
        )

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
            f"Тип объекта:{type(homeworks)}"
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
        raise KeyError("Недокументированный статус "
                       f"домашней работы: {homework_status}")

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = [
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    ]

    check_token = True

    for name, value in tokens:
        if value is None:
            logging.critical(f"Токен {name} недоступен!")
            check_token = False
    return check_token


def get_current_time():
    """Создание точки отсчета для последующих запросов."""
    payload = {"url": ENDPOINT, "headers": HEADERS, "params": {"from_date": 0}}
    response: requests.models.Response = requests.get(**payload)
    try:
        response_json = response.json()
        last_homework = response_json["homeworks"][0]
        if last_homework["status"] == "approved":
            return response_json["current_date"]
        date_: str = last_homework["date_updated"]
        return datetime.fromisoformat(date_[:-1])
    except Exception:
        return int(datetime.datetime.utcnow().timestamp())


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise TokensError("Ошибка в токенах!!")

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = get_current_time()

    message_before = None
    message_error_before = None
    message = None
    message_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            current_timestamp = response.get('current_date', int(time.time()))

            if homeworks:
                message = parse_status(homeworks[0])

            if message != message_before:
                send_message(bot, message)
                message_before = message
            else:
                logging.debug("Статус домашней работы не обновился.")

        except Exception as error:
            logging.error(error)
            message_error = f"Сбой в работе программы. {error}"

            if message_error != message_error_before:
                send_message(bot, message_error)
                message_error_before = message_error

        finally:
            time.sleep(RETRY_TIME)


if __name__ == "__main__":
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'hwbot_log.log'
    )

    logging.basicConfig(
        level=logging.DEBUG,
        format=("%(asctime)s - [%(levelname)s] "
                "- %(funcName)s(%(lineno)d) - %(message)s"),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(filename=log_path),
        ],
    )

    main()
