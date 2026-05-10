from core.auth import AuthManager
from core.api import BingXAPI
import json
auth = AuthManager()
api = BingXAPI(auth)
resp = api.get_balance()
print(json.dumps(resp, indent=2, default=str))
