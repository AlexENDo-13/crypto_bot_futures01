from filters.base import BaseFilter
from strategies.base import Signal
from datetime import datetime, timezone

class SessionFilter(BaseFilter):
    NAME = "SessionFilter"
    DESCRIPTION = "Allows trading only during specified sessions"
    PRIORITY = 10
    PARAMS = {'enabled': True, 'allowed_sessions': ['Asian', 'European', 'American']}

    def assess(self, signal: Signal, data: dict) -> float:
        now = datetime.now(timezone.utc).hour
        allowed = self.config['allowed_sessions']
        session_map = {'Asian': (0, 8), 'European': (8, 16), 'American': (16, 24)}
        current_session = None
        for ses, (start, end) in session_map.items():
            if start <= now < end:
                current_session = ses
                break
        if current_session not in allowed:
            return 0.0
        return signal.confidence
