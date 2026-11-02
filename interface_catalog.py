"""Static English vocabulary shared by presentation and built-in search. No network."""
import json
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def englishCatalog():
    return json.loads((Path(__file__).resolve().parent/'assets'/'i18n_en.json').read_text(encoding='utf-8'))


def english(value):
    return englishCatalog().get(value,value) if isinstance(value,str) else value
