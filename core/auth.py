"""
API key management for BingX.
Loads keys from keys.json (excluded from git and exports).
"""
import json
import os
from typing import Optional, Dict


class AuthManager:
    """Manages API authentication credentials."""
    
    KEYS_FILE = 'keys.json'
    
    def __init__(self):
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._demo_mode: bool = True
        self.load_keys()
    
    def load_keys(self) -> bool:
        """Load API keys from keys.json."""
        try:
            if os.path.exists(self.KEYS_FILE):
                with open(self.KEYS_FILE, 'r') as f:
                    data = json.load(f)
                self._api_key = data.get('api_key', '').strip()
                self._api_secret = data.get('api_secret', '').strip()
                self._demo_mode = not (self._api_key and self._api_secret)
                return not self._demo_mode
        except Exception as e:
            print(f"Error loading keys: {e}")
        self._demo_mode = True
        return False
    
    def save_keys(self, api_key: str, api_secret: str) -> bool:
        """Save API keys to keys.json."""
        try:
            data = {
                'api_key': api_key.strip(),
                'api_secret': api_secret.strip()
            }
            with open(self.KEYS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            self._api_key = api_key.strip()
            self._api_secret = api_secret.strip()
            self._demo_mode = False
            return True
        except Exception as e:
            print(f"Error saving keys: {e}")
            return False
    
    @property
    def api_key(self) -> Optional[str]:
        return self._api_key
    
    @property
    def api_secret(self) -> Optional[str]:
        return self._api_secret
    
    @property
    def demo_mode(self) -> bool:
        return self._demo_mode
    
    def get_keys_dict(self) -> Dict[str, Optional[str]]:
        """Return keys as dict for API requests."""
        return {
            'api_key': self._api_key,
            'api_secret': self._api_secret
        }
    
    def test_connection(self) -> bool:
        """Test API connection with loaded keys."""
        if self._demo_mode:
            return False
        try:
            from core.api import BingXAPI
            api = BingXAPI(self)
            api.get_balance()
            return True
        except Exception:
            return False


# Singleton instance
_auth_instance: Optional[AuthManager] = None


def get_auth() -> AuthManager:
    """Get or create AuthManager singleton."""
    global _auth_instance
    if _auth_instance is None:
        _auth_instance = AuthManager()
    return _auth_instance
