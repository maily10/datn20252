import os
import yaml


def create_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def read_file(path: str):
    with open(path, encoding="utf-8") as file:
        for line in file:
            yield line.rstrip("\n")


def init_output_dirs(output_dpath: str):
    create_dir(output_dpath)
    urls_dpath = "/".join([output_dpath, "urls"])
    create_dir(urls_dpath)
    return urls_dpath, output_dpath


def get_config(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config
