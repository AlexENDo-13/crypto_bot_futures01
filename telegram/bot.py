"""
Optional Telegram bot for remote notifications and control.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Optional: python-telegram-bot or requests-based implementation
TELEGRAM_AVAILABLE = False

try:
    import requests
    TELEGRAM_AVAILABLE = True
except ImportError:
    pass


class TelegramBot:
    """
    Telegram bot for remote notifications.
    Uses Bot API directly via requests (no external dependency).
    """
    
    API_BASE = "https://api.telegram.org/bot{token}/{method}"
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)
        self._bot_info: Optional[dict] = None
    
    def configure(self, token: str, chat_id: str):
        """Configure bot credentials."""
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        
        if self.enabled:
            self._test_connection()
    
    def _test_connection(self) -> bool:
        """Test Telegram API connection."""
        if not TELEGRAM_AVAILABLE:
            logger.warning("requests library not available for Telegram")
            return False
        
        try:
            url = self.API_BASE.format(token=self.token, method='getMe')
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                self._bot_info = response.json().get('result', {})
                logger.info(f"Telegram bot connected: @{self._bot_info.get('username', 'unknown')}")
                return True
            else:
                logger.error(f"Telegram connection failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram connection error: {e}")
            return False
    
    def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Send a text message."""
        if not self.enabled or not TELEGRAM_AVAILABLE:
            return False
        
        try:
            url = self.API_BASE.format(token=self.token, method='sendMessage')
            data = {
                'chat_id': self.chat_id,
                'text': text[:4096],  # Telegram limit
                'parse_mode': parse_mode,
                'disable_web_page_preview': True,
            }
            response = requests.post(url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    
    def send_trade_notification(self, symbol: str, action: str, price: float, 
                                 pnl: Optional[float] = None):
        """Send trade notification."""
        emoji = "🟢" if action == "BUY" else "🔴"
        pnl_text = f"\nPnL: {pnl:+.2f}" if pnl is not None else ""
        
        text = f"""
{emoji} <b>Trade {action}</b>

Symbol: <code>{symbol}</code>
Price: {price:.6f}{pnl_text}
        """.strip()
        
        self.send_message(text)
    
    def send_daily_report(self, stats: dict):
        """Send daily PnL report."""
        pnl = stats.get('daily_pnl', 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        
        text = f"""
📊 <b>Daily Report</b>

PnL: {pnl_emoji} {pnl:+.2f} USDT
Trades: {stats.get('total_trades', 0)}
Winrate: {stats.get('winrate', 0):.1f}%
Open Positions: {stats.get('open_positions', 0)}
Drawdown: {stats.get('current_drawdown_pct', 0):.2f}%
        """.strip()
        
        self.send_message(text)
    
    def send_alert(self, message: str, level: str = "warning"):
        """Send alert notification."""
        emojis = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '🚨',
            'success': '✅',
        }
        emoji = emojis.get(level, '⚠️')
        
        text = f"{emoji} <b>Alert</b>\n\n{message}"
        self.send_message(text)
