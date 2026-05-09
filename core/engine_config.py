import os
import shutil
import logging
from configparser import ConfigParser

logger = logging.getLogger(__name__)

CONFIG_FILE = 'config.ini'
CONFIG_BACKUP = 'config.ini.bak'


def load_config(engine):
    cfg = ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        return

    cfg.read(CONFIG_FILE)
    try:
        if cfg.has_section('ENGINE'):
            engine.scan_interval = cfg.getint('ENGINE', 'scan_interval', fallback=60)
            engine.signal_threshold = cfg.getfloat('ENGINE', 'signal_threshold', fallback=0.5)
            engine.max_positions = cfg.getint('ENGINE', 'max_positions', fallback=8)
            engine.timeframes = cfg.get('ENGINE', 'timeframes', fallback='15m,1h,4h').split(',')
            engine.top_n_symbols = cfg.getint('ENGINE', 'top_symbols', fallback=50)

        if cfg.has_section('RISK'):
            profile = cfg.get('RISK', 'profile', fallback='SmartTurbo')
            engine.risk_manager.set_profile(profile)

            risk_pct = cfg.getfloat('RISK', 'risk_per_trade', fallback=None)
            max_lev = cfg.getint('RISK', 'max_leverage', fallback=None)

            if risk_pct is not None:
                engine.risk_manager.risk_per_trade_pct = risk_pct
            if max_lev is not None:
                engine.risk_manager.max_leverage = max_lev

            engine.risk_manager.set_user_limits(
                risk_pct=risk_pct or engine.risk_manager.risk_per_trade_pct,
                max_lev=max_lev or engine.risk_manager.max_leverage,
                max_pos=engine.max_positions
            )

            if cfg.has_option('RISK', 'use_day_profile'):
                engine.risk_manager.use_day_profile = cfg.getboolean('RISK', 'use_day_profile')
            if cfg.has_option('RISK', 'kelly_enabled'):
                engine.risk_manager._kelly_enabled = cfg.getboolean('RISK', 'kelly_enabled')
            if cfg.has_option('RISK', 'kelly_winrate'):
                engine.risk_manager._kelly_winrate = cfg.getfloat('RISK', 'kelly_winrate')
            if cfg.has_option('RISK', 'kelly_avg_win_loss'):
                engine.risk_manager._kelly_avg_win_loss_ratio = cfg.getfloat('RISK', 'kelly_avg_win_loss')

        if cfg.has_section('TRADING'):
            engine.trailing_sl_enabled = cfg.getboolean('TRADING', 'trailing_sl', fallback=True)
            engine.trailing_distance_pct = cfg.getfloat('TRADING', 'trailing_distance_pct', fallback=0.5)
            engine.partial_close_enabled = cfg.getboolean('TRADING', 'partial_close', fallback=True)
            engine.partial_close_pct = cfg.getfloat('TRADING', 'partial_close_pct', fallback=50.0)
            engine.breakeven_enabled = cfg.getboolean('TRADING', 'breakeven', fallback=True)
            engine.breakeven_atr_mult = cfg.getfloat('TRADING', 'breakeven_atr_mult', fallback=1.0)
            engine.slippage_timeout_sec = cfg.getfloat('TRADING', 'slippage_timeout', fallback=10.0)
            engine.reinvest_profits = cfg.getboolean('TRADING', 'reinvest_profits', fallback=True)

        logger.debug("Configuration loaded")
    except Exception as e:
        logger.error(f"Error loading config: {e}")


def save_config(engine):
    try:
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
    except Exception:
        pass

    cfg = ConfigParser()
    if os.path.exists(CONFIG_FILE):
        cfg.read(CONFIG_FILE)

    for section in ['ENGINE', 'RISK', 'TRADING']:
        if not cfg.has_section(section):
            cfg.add_section(section)

    cfg.set('ENGINE', 'scan_interval', str(engine.scan_interval))
    cfg.set('ENGINE', 'signal_threshold', str(engine.signal_threshold))
    cfg.set('ENGINE', 'max_positions', str(engine.max_positions))
    cfg.set('ENGINE', 'timeframes', ','.join(engine.timeframes))
    cfg.set('ENGINE', 'top_symbols', str(engine.top_n_symbols))

    cfg.set('RISK', 'risk_per_trade', str(engine.risk_manager.risk_per_trade_pct))
    cfg.set('RISK', 'max_leverage', str(engine.risk_manager.max_leverage))
    cfg.set('RISK', 'profile', engine.risk_manager._current_profile)
    cfg.set('RISK', 'use_day_profile', str(engine.risk_manager.use_day_profile))
    cfg.set('RISK', 'kelly_enabled', str(engine.risk_manager._kelly_enabled))
    cfg.set('RISK', 'kelly_winrate', str(engine.risk_manager._kelly_winrate))
    cfg.set('RISK', 'kelly_avg_win_loss', str(engine.risk_manager._kelly_avg_win_loss_ratio))

    cfg.set('TRADING', 'trailing_sl', str(engine.trailing_sl_enabled))
    cfg.set('TRADING', 'trailing_distance_pct', str(engine.trailing_distance_pct))
    cfg.set('TRADING', 'partial_close', str(engine.partial_close_enabled))
    cfg.set('TRADING', 'partial_close_pct', str(engine.partial_close_pct))
    cfg.set('TRADING', 'breakeven', str(engine.breakeven_enabled))
    cfg.set('TRADING', 'breakeven_atr_mult', str(engine.breakeven_atr_mult))
    cfg.set('TRADING', 'slippage_timeout', str(engine.slippage_timeout_sec))
    cfg.set('TRADING', 'reinvest_profits', str(engine.reinvest_profits))

    with open(CONFIG_FILE, 'w') as f:
        cfg.write(f)
    logger.debug("Configuration saved")
