import logging
import importlib
import pkgutil
import inspect
from typing import Dict

from strategies.base import BaseStrategy
from indicators.base import BaseIndicator
from filters.base import BaseFilter

logger = logging.getLogger(__name__)


def init_components(engine):
    engine.scheduler.register_callback('night_mode_on', engine._on_night_mode_on)
    engine.scheduler.register_callback('night_mode_off', engine._on_night_mode_off)
    engine.scheduler.register_callback('session_change', engine._on_session_change)
    engine.scheduler.register_callback('new_day', engine._on_new_day)

    engine.scheduler.register_task('market_scan', engine.scan_interval, engine._market_scan_task, enabled=True)
    engine.scheduler.register_task('weight_update', 3600, engine._update_weights_task, enabled=True)
    engine.scheduler.register_task('equity_update', 60, engine._equity_update_task, enabled=True)
    engine.scheduler.register_task('position_sync', 30, engine._sync_positions_task, enabled=True)
    engine.scheduler.register_task('watchdog_heartbeat', 10, engine._heartbeat_task, enabled=True)


def load_all_modules(engine):
    logger.info("Loading modules...")
    engine.strategies = _load_from_package('strategies', BaseStrategy)
    engine.indicators = _load_from_package('indicators', BaseIndicator)
    engine.filters = _load_from_package('filters', BaseFilter)

    for name, strategy in engine.strategies.items():
        engine.voting.register_strategy(name, getattr(strategy, 'weight', 1))

    logger.info(f"Loaded: {len(engine.strategies)} strategies, {len(engine.indicators)} indicators, {len(engine.filters)} filters")


def _load_from_package(package_name, base_class):
    modules = {}
    try:
        package = importlib.import_module(package_name)
        package_path = package.__path__
    except Exception as e:
        logger.error(f"Failed to import package {package_name}: {e}")
        return modules

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        if module_name == 'base' or module_name.startswith('_'):
            continue
        full_name = f"{package_name}.{module_name}"
        try:
            mod = importlib.import_module(full_name)
        except Exception as e:
            logger.error(f"Failed to import {full_name}: {e}")
            continue

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if not issubclass(obj, base_class) or obj is base_class:
                continue
            if name.startswith('Base'):
                continue
            try:
                instance = obj()
                modules[getattr(instance, 'NAME', name)] = instance
                logger.info(f"  Loaded {base_class.__name__}: {getattr(instance, 'NAME', name)}")
            except Exception as e:
                logger.warning(f"  Failed to instantiate {name}: {e}")

    return modules
