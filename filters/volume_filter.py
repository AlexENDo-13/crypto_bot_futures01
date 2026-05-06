from filters.base import BaseFilter
from strategies.base import Signal

class VolumeFilter(BaseFilter):
    NAME = "VolumeFilter"
    DESCRIPTION = "Filters low-volume signals"
    PRIORITY = 40
    PARAMS = {'enabled': True, 'min_volume_ratio': 0.7}

    def assess(self, signal: Signal, data: dict) -> float:
        volume_ratio = data.get('volume_ratio', 1.0)
        if volume_ratio < self.config['min_volume_ratio']:
            return 0.0
        return signal.confidence
