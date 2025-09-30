import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from . import prioritysieve_globals
from .morpheme import Morpheme


def print_stacktrace() -> None:
    stacktrace = ""
    for thread in threading.enumerate():
        assert thread.ident is not None
        stacktrace += str(thread)
        stacktrace += "".join(
            traceback.format_stack(sys._current_frames()[thread.ident])
        )
    print(f"stacktrace: {stacktrace}")


def print_thread_name() -> None:
    print(f"thread name: {threading.current_thread().name}")


def save_to_json_file(file_path: Path, _dict: dict[tuple[str, str, str], int]) -> None:
    # the json module only does not support dict with tuple keys,
    # so we have to convert the keys to single strings and then
    # reverse the process when loading them later
    dict_with_str_keys = {"|".join(k): v for k, v in _dict.items()}

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(dict_with_str_keys, file, ensure_ascii=False, indent=4)


def load_dict_from_json_file(file_path: Path) -> dict[Any, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        dict_from_file = json.load(file)
        assert isinstance(dict_from_file, dict)

        # Convert the string keys back to tuples, supporting legacy 2-part keys
        _dict: dict[tuple[str, ...], Any] = {}
        for key, value in dict_from_file.items():
            parts = key.split("|")
            if len(parts) == 2:
                parts.append("")
            _dict[tuple(parts)] = value
        return _dict


def print_current_directory() -> None:
    print(f"Current Directory: {Path.cwd()}")


def print_directory_tree(root_dir: str, indent: str = "") -> None:
    """
    Print the directory tree rooted at root_dir with a specified indentation.
    """
    if not os.path.exists(root_dir):
        print(f"Directory '{root_dir}' does not exist.")
        return

    print(indent + os.path.basename(root_dir) + os.path.sep)
    indent += "│   "

    items = os.listdir(root_dir)
    items.sort(key=lambda x: os.path.isfile(os.path.join(root_dir, x)), reverse=True)

    for index, item in enumerate(items):
        if index == len(items) - 1:
            new_indent = indent[:-1] + "└── "
        else:
            new_indent = indent[:-1] + "├── "

        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            print(new_indent + item + os.path.sep)
            print_directory_tree(item_path, indent + "    ")
        else:
            print(new_indent + item)


def dev_print(message: str) -> None:
    if prioritysieve_globals.DEV_MODE:
        print(message)


def dev_print_morphs(morphs: list[Morpheme]) -> None:
    if prioritysieve_globals.DEV_MODE:
        for morph in morphs:
            print(f"morph: {morph.inflection}")
