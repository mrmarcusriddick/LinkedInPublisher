"""Load only the credential belonging to the requested publishing destination."""
import json
from datetime import datetime, timedelta

SECRET_NAMES = {'personal': 'linkedin-token-personal', 'company': 'linkedin-token-company'}

def load_target_token(client, target, now):
    # No fallback to the legacy shared token or the other destination's token.
    name = SECRET_NAMES[target]
    auth = json.loads(client.get_secret(name).value)
    token = auth.get('access_token')
    expiry = datetime.fromisoformat(auth['expires_at'])
    if not isinstance(token, str) or not token.strip():
        raise ValueError('Empty token')
    if expiry.tzinfo is None or expiry <= now + timedelta(minutes=5):
        raise ValueError('Token expired or too close to expiry; reauthorize this destination')
    return auth
