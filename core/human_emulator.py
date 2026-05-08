"""
Human Behaviour Emulator – эмуляция действий живого трейдера.
Делает поведение бота неотличимым от ручной торговли для анти-слежения биржи.
"""
import random
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class HumanEmulator:
    """
    Централизованный эмулятор человеческого поведения.
    Управляет всеми аспектами имитации: задержки, рандомизация,
    пропуски действий, разбивка ордеров, плавающие настройки.
    
    Подключение к движку:
        engine.human_emulator = HumanEmulator(engine)
        engine.human_emulator.start()
    """

    # ------------------------------------------------------------------
    # Параметры по умолчанию (переопределяются из config.ini)
    # ------------------------------------------------------------------
    # User-Agent rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Vivaldi/6.5.3206.59",
    ]

    # ------------------------------------------------------------------
    def __init__(self, engine):
        self.engine = engine
        self._running = False

        # --- Параметры из секции [HUMAN] config.ini (загружаются ниже) ---
        self.ua_rotation: bool = True
        self.ua_rotation_interval_minutes: int = 45          # как часто менять User-Agent

        # Задержки между действиями (секунды)
        self.interface_delay_min: float = 0.3
        self.interface_delay_max: float = 1.2
        self.scan_jitter_min: float = 5                     # добавляется к scan_interval
        self.scan_jitter_max: float = 30
        self.portfolio_check_jitter_min: float = 10
        self.portfolio_check_jitter_max: float = 60

        # Таймфреймы
        self.tf_randomization: bool = True
        self.tf_pool: List[str] = ['15m', '1h', '4h', '1d']
        self.tf_min_count: int = 2
        self.tf_max_count: int = 4

        # Нелинейная задержка API
        self.api_thinking_min: float = 0.05
        self.api_thinking_max: float = 0.4
        self.api_thinking_clusters: bool = True

        # Режимы
        self.weekend_mode: bool = True
        self.idle_mode: bool = True
        self.idle_skip_chance: float = 0.10
        self.idle_cancel_chance: float = 0.05

        # Разбивка ордеров
        self.split_entry_enabled: bool = True
        self.split_parts_min: int = 2
        self.split_parts_max: int = 4
        self.split_delay_min: float = 5.0
        self.split_delay_max: float = 30.0

        # Случайные корректировки SL/TP
        self.tweak_tpsl_enabled: bool = True
        self.tweak_percent: float = 0.001                  # ±0.1% от цены

        # Отмены ордеров
        self.random_cancel_enabled: bool = True
        self.random_cancel_probability: float = 0.02        # 2% шанс на итерацию

        # Частота проверок
        self.check_frequency_day: int = 2                   # раз в час
        self.check_frequency_night: int = 1                 # раз в час
        self.check_frequency_weekend: int = 1

        # Постепенное изменение настроек
        self.gradual_tweak_enabled: bool = True
        self.gradual_step_max: float = 0.05                 # максимальный шаг

        # Рабочие переменные
        self._ua_index: int = 0
        self._last_ua_rotation: float = 0.0
        self._last_scan_time: float = 0.0
        self._last_portfolio_check: float = 0.0
        self._scan_interval_cache: float = 0.0
        self._portfolio_check_interval_cache: float = 0.0

        # Загрузка конфигурации
        self._load_config()

    def _load_config(self):
        """Читает секцию [HUMAN] из config.ini."""
        try:
            from configparser import ConfigParser
            cfg = ConfigParser()
            cfg.read('config.ini')
            if not cfg.has_section('HUMAN'):
                logger.info("HumanEmulator: секция [HUMAN] не найдена, используются значения по умолчанию")
                return
            c = cfg['HUMAN']
            self.ua_rotation = c.getboolean('ua_rotation', self.ua_rotation)
            self.ua_rotation_interval_minutes = c.getint('ua_rotation_interval_minutes', self.ua_rotation_interval_minutes)
            self.interface_delay_min = c.getfloat('interface_delay_min', self.interface_delay_min)
            self.interface_delay_max = c.getfloat('interface_delay_max', self.interface_delay_max)
            self.scan_jitter_min = c.getfloat('scan_jitter_min', self.scan_jitter_min)
            self.scan_jitter_max = c.getfloat('scan_jitter_max', self.scan_jitter_max)
            self.portfolio_check_jitter_min = c.getfloat('portfolio_check_jitter_min', self.portfolio_check_jitter_min)
            self.portfolio_check_jitter_max = c.getfloat('portfolio_check_jitter_max', self.portfolio_check_jitter_max)
            self.tf_randomization = c.getboolean('tf_randomization', self.tf_randomization)
            self.tf_min_count = c.getint('tf_min_count', self.tf_min_count)
            self.tf_max_count = c.getint('tf_max_count', self.tf_max_count)
            self.api_thinking_min = c.getfloat('api_thinking_min', self.api_thinking_min)
            self.api_thinking_max = c.getfloat('api_thinking_max', self.api_thinking_max)
            self.api_thinking_clusters = c.getboolean('api_thinking_clusters', self.api_thinking_clusters)
            self.weekend_mode = c.getboolean('weekend_mode', self.weekend_mode)
            self.idle_mode = c.getboolean('idle_mode', self.idle_mode)
            self.idle_skip_chance = c.getfloat('idle_skip_chance', self.idle_skip_chance)
            self.idle_cancel_chance = c.getfloat('idle_cancel_chance', self.idle_cancel_chance)
            self.split_entry_enabled = c.getboolean('split_entry_enabled', self.split_entry_enabled)
            self.split_parts_min = c.getint('split_parts_min', self.split_parts_min)
            self.split_parts_max = c.getint('split_parts_max', self.split_parts_max)
            self.split_delay_min = c.getfloat('split_delay_min', self.split_delay_min)
            self.split_delay_max = c.getfloat('split_delay_max', self.split_delay_max)
            self.tweak_tpsl_enabled = c.getboolean('tweak_tpsl_enabled', self.tweak_tpsl_enabled)
            self.tweak_percent = c.getfloat('tweak_percent', self.tweak_percent)
            self.random_cancel_enabled = c.getboolean('random_cancel_enabled', self.random_cancel_enabled)
            self.random_cancel_probability = c.getfloat('random_cancel_probability', self.random_cancel_probability)
            self.check_frequency_day = c.getint('check_frequency_day', self.check_frequency_day)
            self.check_frequency_night = c.getint('check_frequency_night', self.check_frequency_night)
            self.check_frequency_weekend = c.getint('check_frequency_weekend', self.check_frequency_weekend)
            self.gradual_tweak_enabled = c.getboolean('gradual_tweak_enabled', self.gradual_tweak_enabled)
            self.gradual_step_max = c.getfloat('gradual_step_max', self.gradual_step_max)
            logger.info("HumanEmulator config loaded from config.ini")
        except Exception as e:
            logger.warning(f"HumanEmulator: ошибка загрузки конфига: {e}")

    def start(self):
        self._running = True
        logger.info("HumanEmulator activated")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # 1. User-Agent rotation
    # ------------------------------------------------------------------
    def get_user_agent(self) -> str:
        """Возвращает текущий User-Agent с ротацией."""
        if not self.ua_rotation:
            return self.engine.antidetect.get_user_agent()
        now = time.time()
        if now - self._last_ua_rotation > self.ua_rotation_interval_minutes * 60:
            self._ua_index = (self._ua_index + 1) % len(self.USER_AGENTS)
            self._last_ua_rotation = now
            logger.debug(f"HumanEmulator: User-Agent rotated to index {self._ua_index}")
        return self.USER_AGENTS[self._ua_index]

    # ------------------------------------------------------------------
    # 2. Задержки между действиями
    # ------------------------------------------------------------------
    def interface_delay(self):
        """Эмулирует задержку между кликами в интерфейсе."""
        time.sleep(random.uniform(self.interface_delay_min, self.interface_delay_max))

    def scan_jitter(self) -> float:
        """Возвращает добавочное время к scan_interval."""
        return random.uniform(self.scan_jitter_min, self.scan_jitter_max)

    def portfolio_check_jitter(self) -> float:
        """Возвращает добавочное время к интервалу проверки портфеля."""
        return random.uniform(self.portfolio_check_jitter_min, self.portfolio_check_jitter_max)

    # ------------------------------------------------------------------
    # 3. Случайное изменение количества таймфреймов
    # ------------------------------------------------------------------
    def get_randomized_timeframes(self, base_timeframes: List[str]) -> List[str]:
        """Выбирает случайное подмножество таймфреймов из пула."""
        if not self.tf_randomization:
            return base_timeframes
        count = random.randint(self.tf_min_count, min(self.tf_max_count, len(self.tf_pool)))
        selected = random.sample(self.tf_pool, count)
        logger.debug(f"HumanEmulator: randomized timeframes: {selected}")
        return selected

    # ------------------------------------------------------------------
    # 4. Нелинейная задержка между API-запросами
    # ------------------------------------------------------------------
    def api_thinking_delay(self):
        """Имитирует 'задумчивость' трейдера с кластеризацией."""
        delay = random.uniform(self.api_thinking_min, self.api_thinking_max)
        if self.api_thinking_clusters and random.random() < 0.3:
            delay *= 2.5  # иногда залипает
        time.sleep(delay)

    # ------------------------------------------------------------------
    # 5. Режимы "выходного дня" и "праздности"
    # ------------------------------------------------------------------
    def is_weekend(self) -> bool:
        """Проверяет, выходные ли сейчас (суббота/воскресенье)."""
        now = datetime.now(timezone.utc)
        return now.weekday() >= 5

    def should_skip_action(self) -> bool:
        """Решает, нужно ли пропустить очередное действие (режим праздности)."""
        if not self.idle_mode:
            return False
        if self.is_weekend() and self.weekend_mode:
            return random.random() < self.idle_skip_chance * 2.5
        return random.random() < self.idle_skip_chance

    def should_cancel_action(self) -> bool:
        """Решает, нужно ли симулировать отмену действия."""
        if not self.idle_mode:
            return False
        return random.random() < self.idle_cancel_chance

    # ------------------------------------------------------------------
    # 6. Эмуляция ручного входа с разбивкой
    # ------------------------------------------------------------------
    def split_entry_quantity(self, total_qty: float) -> List[Tuple[float, float]]:
        """
        Разбивает общее количество на несколько частей со случайными задержками.
        Возвращает список: [(количество, задержка), ...]
        """
        if not self.split_entry_enabled:
            return [(total_qty, 0.0)]
        parts = random.randint(self.split_parts_min, self.split_parts_max)
        if parts <= 1:
            return [(total_qty, 0.0)]
        # Распределяем с небольшим разбросом
        base = total_qty / parts
        splits = []
        remaining = total_qty
        for i in range(parts - 1):
            qty = base * random.uniform(0.7, 1.3)
            qty = round(qty, 8)
            if qty <= 0:
                qty = base
            remaining -= qty
            delay = random.uniform(self.split_delay_min, self.split_delay_max)
            splits.append((qty, delay))
        splits.append((remaining, 0.0))  # последняя часть без задержки
        logger.debug(f"HumanEmulator: split entry into {len(splits)} parts")
        return splits

    # ------------------------------------------------------------------
    # 7. Случайные корректировки параметров ордеров
    # ------------------------------------------------------------------
    def tweak_price(self, price: float) -> float:
        """Слегка изменяет цену (SL/TP) на случайный процент."""
        if not self.tweak_tpsl_enabled or price <= 0:
            return price
        factor = 1.0 + random.uniform(-self.tweak_percent, self.tweak_percent)
        return round(price * factor, 8)

    # ------------------------------------------------------------------
    # 8. Симуляция "человеческих" отмен ордеров
    # ------------------------------------------------------------------
    def should_random_cancel(self) -> bool:
        """Случайным образом решает, отменить ли ордер."""
        if not self.random_cancel_enabled:
            return False
        return random.random() < self.random_cancel_probability

    # ------------------------------------------------------------------
    # 9. Реалистичная частота проверок
    # ------------------------------------------------------------------
    def get_check_interval(self) -> float:
        """
        Возвращает интервал проверки (в секундах) в зависимости от времени суток.
        Днём – чаще, ночью – реже, на выходных – ещё реже.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        if self.is_weekend():
            base_per_hour = self.check_frequency_weekend
        elif 6 <= hour < 22:
            base_per_hour = self.check_frequency_day
        else:
            base_per_hour = self.check_frequency_night
        if base_per_hour <= 0:
            base_per_hour = 1
        # Преобразуем проверок в час -> интервал в секундах
        interval = 3600.0 / base_per_hour
        # Добавляем случайный разброс ±30%
        interval *= random.uniform(0.7, 1.3)
        return max(30, interval)  # не чаще чем раз в 30 секунд

    # ------------------------------------------------------------------
    # 10. Постепенное изменение настроек
    # ------------------------------------------------------------------
    def gradual_tweak_parameter(self, current_value: float, target_value: float) -> float:
        """
        Медленно сдвигает параметр в сторону целевого значения.
        Используется для эмуляции ручной подстройки.
        """
        if not self.gradual_tweak_enabled:
            return target_value
        diff = target_value - current_value
        step = max(0.01, min(abs(diff) * random.uniform(0.1, 0.5), self.gradual_step_max))
        if abs(diff) <= step:
            return target_value
        return current_value + step * (1 if diff > 0 else -1)
