from contextlib import contextmanager
from time import perf_counter
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@contextmanager
def timer(name: str, show_time: bool = False):
    start = perf_counter()
    if show_time:
        logger.info("[%s] Start  %s", name, datetime.now().strftime("%H:%M:%S.%f")[:-3])
    else:
        logger.info("[%s] Start", name)
    try:
        yield
    finally:
        end = perf_counter()
        if show_time:
            logger.info(
                "[%s] End    %s (%.3f s)", 
                name,  datetime.now().strftime("%H:%M:%S.%f")[:-3], end - start
            )
        else:
            logger.info("[%s] End    (%.3f s)", name, end - start)
