import time

from pydantic import ValidationError


def wait_while_not(func, timeout=300, interval=2):
    """
    Excecutes func until it returns True or timeout is reached
    :param func: Excecutable function
    :param timeout: Timeout in seconds
    :param interval: Interval between function calls
    :return: result of function if func returned True, False otherwise
    """
    ex = None
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = func()
            if result:
                return result
        except ValidationError as ve:
            raise ve
        except Exception as e:
            ex = e
        time.sleep(interval)
    if ex:
        raise ex
    else:
        return False