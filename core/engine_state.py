import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

STATE_FILE = 'data/engine_state.json'
BLACKLIST_FILE = 'data/blacklist.json'


def load_state(engine):
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
        engine.risk_controller.daily_pnl = data.get('daily_pnl', 0.0)
        engine.risk_controller.last_day = data.get('last_day', datetime.now(timezone.utc).day)
        # стратегии отключённые пока не восстанавливаем, т.к. VotingSystem сам управляет
    except Exception as e:
        logger.error(f"Failed to load state: {e}")


def save_state(engine):
    data = {
        'daily_pnl': engine.risk_controller.daily_pnl,
        'last_day': engine.risk_controller.last_day,
        'updated': datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


def load_blacklist(engine):
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE) as f:
                engine._blacklist = json.load(f).get('symbols', [])
    except Exception:
        engine._blacklist = []


def save_blacklist(engine):
    try:
        with open(BLACKLIST_FILE, 'w') as f:
            json.dump({
                'symbols': engine._blacklist,
                'updated': datetime.now(timezone.utc).isoformat()
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save blacklist: {e}")
