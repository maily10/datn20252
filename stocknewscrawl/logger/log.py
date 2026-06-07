import yaml
import logging
import logging.config
from pathlib import Path

from utils.utils import create_dir


def setup_logging(log_dir: str, config_fpath: str = "logger/logger_config.yml"):
    create_dir(log_dir)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    log_config = Path(config_fpath)
    if log_config.is_file():
        with open(log_config, "r") as f:
            config = yaml.safe_load(f.read())
        for __, handler in config["handlers"].items():
            if "filename" in handler:
                handler["filename"] = "/".join([log_dir, handler["filename"]])
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO)
        print(f"Warning: logging config not found at {log_config}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
