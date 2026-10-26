"""Единая папка данных, не зависящая от текущей рабочей директории."""
import os
from pathlib import Path

DATA_DIRECTORY = Path(
    os.environ.get("LEPKA_DATA_DIR")
    or os.environ.get("FLET_APP_STORAGE_DATA")
    or Path(__file__).resolve().parent
).expanduser().resolve()
DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
