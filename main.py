import logging
import sys

import bot


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot.log"),
        ],
    )


if __name__ == "__main__":
    setup_logging()
    try:
        bot.run()
    except KeyboardInterrupt:
        logging.getLogger("bot").info("Shutting down.")
