"""Daily schedule and conservative publishing state machine (no Azure dependency)."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/New_York')
TARGETS = ('personal', 'company')

def validate(item):
    if set(item) != {'date', 'posts', 'sources'}:
        raise ValueError('Expected date, posts, sources only')
    day = date.fromisoformat(item['date'])
    if day.isoformat() != item['date']:
        raise ValueError('Date must be YYYY-MM-DD')
    if set(item['posts']) != set(TARGETS):
        raise ValueError('Exactly personal and company posts required')
    for target in TARGETS:
        body = item['posts'][target]
        if not isinstance(body, str) or not body.strip() or len(body) > 3000:
            raise ValueError('Each post must contain 1-3000 characters')
    if item['posts']['personal'].strip() == item['posts']['company'].strip():
        raise ValueError('Tailor the two posts to their audiences')
    if not isinstance(item['sources'], list) or not item['sources']:
        raise ValueError('At least one source required')
    for source in item['sources']:
        if not isinstance(source, str) or not source.startswith('https://'):
            raise ValueError('Sources must be HTTPS URLs')
    return item

def canonical(item):
    return json.dumps(validate(item), sort_keys=True, ensure_ascii=False).encode()

def due_at(day):
    return datetime.combine(date.fromisoformat(day), time(9), ZONE).astimezone(timezone.utc)

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def process(item, target, state, save, send, now, *, manual=False, attachment=None):
    """Caller holds exclusive durable lock. Never retry an ambiguous delivery."""
    validate(item)
    if target not in TARGETS:
        raise ValueError('Unknown target')
    due = due_at(item['date'])
    if not manual and now < due:
        return 'not_due'
    if not manual and now >= due + timedelta(hours=1):
        return 'outside_window'
    text = item['posts'][target]
    from app.media import attachment_hash
    content_hash = attachment_hash(text, attachment)
    if state.get('content_hash') and state['content_hash'] != content_hash:
        return 'content_conflict'
    status = state.get('status', 'queued')
    if status == 'sending':
        state.update(status='unknown', reason='Previous execution ended during delivery; reconcile manually')
        save(state)
        return 'unknown'
    if status in ('published', 'unknown', 'blocked'):
        return status
    if state.get('retry_at') and now < datetime.fromisoformat(state['retry_at']):
        return 'waiting_retry'
    state.update(status='sending', content_hash=content_hash, attempted_at=now.isoformat())
    # Persist BEFORE the request. A crash after this point must not cause a second post.
    save(state)
    try:
        result = send(target, text)
    except Exception:
        state.update(status='unknown', reason='Transport failure; delivery may have succeeded')
    else:
        code = result['status']
        if code == 201 and result.get('post_id'):
            state.update(status='published', post_id=result['post_id'], published_at=now.isoformat())
            state.pop('reason', None)
        elif code == 429:
            state.update(status='queued', reason='Rate limited', retry_at=(now + timedelta(seconds=max(300, result.get('retry_after', 300)))).isoformat())
        elif 400 <= code < 500 and code != 408:
            state.update(status='blocked', reason=f'LinkedIn HTTP {code}; correct credentials/permissions/content before manual reset')
        else:
            state.update(status='unknown', reason=f'Ambiguous LinkedIn HTTP {code}; reconcile before manual reset')
    save(state)
    return state['status']
