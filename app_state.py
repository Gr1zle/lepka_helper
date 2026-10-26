import json
from pathlib import Path

STATE_FILE = Path(__file__).with_name('app_state.json')


def getAppState(key, default=None):
    try:
        if not STATE_FILE.exists():
            return default
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return data.get(key, default)
    except Exception:
        return default


def setAppState(key, value):
    try:
        data = {}
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        data[key] = value
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:
        return False
