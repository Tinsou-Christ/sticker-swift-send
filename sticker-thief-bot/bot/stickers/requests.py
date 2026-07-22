import logging
import re

from telegram.error import BadRequest, TelegramError

from .error import EXCEPTIONS

logger = logging.getLogger(__name__)


def raise_exception(received_error_message: str):
    for expected_api_error_message, exception_to_raise in EXCEPTIONS.items():
        if re.search(expected_api_error_message, received_error_message, re.I):
            raise exception_to_raise(received_error_message)

    # raise unknown error if no description matched
    logger.info('unknown exception: %s', received_error_message)
    raise EXCEPTIONS['ext_unknown_api_exception'](received_error_message)


def send_request(func, request_payload: dict):
    try:
        result = func(**request_payload)
        logger.debug('<%s> successfully executed', func.__name__)
        return result
    except (BadRequest, TelegramError) as e:
        logger.error('Telegram exception while trying to execute function <%s>: %s', func.__name__, e.message)
        raise_exception(e.message)
