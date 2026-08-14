"""Gmail OAuth + Send API wrapper.

Uses stdlib urllib.request to avoid adding a Google SDK dependency (keeps
Vercel bundle small).

Flow:
1. connect-start endpoint calls build_oauth_url() and redirects the user
2. Google redirects back to /api/gmail-callback with a code
3. Callback endpoint calls exchange_code_for_tokens() to get refresh_token +
   the connected email address (from the ID token or /userinfo endpoint)
4. Refresh token is stored in gmail_connections table
5. Each send: fetch refresh_token, call refresh_access_token(), then send()

Errors: raise GmailError(public_message). Callers translate to HTTP responses.
"""
import base64
import email.mime.text
import hmac
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
import urllib.request
from typing import Optional

from _lib import env


log = logging.getLogger(__name__)

REDIRECT_URI       = 'https://outboundrun.com/api/gmail-callback'
SCOPES             = 'openid email https://www.googleapis.com/auth/gmail.send'
AUTH_URL           = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL          = 'https://oauth2.googleapis.com/token'
USERINFO_URL       = 'https://www.googleapis.com/oauth2/v3/userinfo'
GMAIL_SEND_URL     = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
STATE_TTL_SECONDS  = 600  # 10 minutes


class GmailError(Exception):
    """Safe-to-return-to-client error. Details logged server-side only."""


# ============================================================================
# STATE HMAC (used to identify the returning user in the OAuth callback)
# ============================================================================

def _state_secret() -> bytes:
    """Reuse an existing server-side secret rather than adding a new env var."""
    return env.SUPABASE_SERVICE_ROLE_KEY.encode('utf-8')


def encode_state(user_id: str) -> str:
    payload = {'uid': user_id, 'ts': int(time.time()), 'nonce': secrets.token_hex(8)}
    payload_json = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode('ascii').rstrip('=')
    sig = hmac.new(_state_secret(), payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
    return f'{payload_b64}.{sig}'


def decode_state(state: str) -> str:
    """Verify state signature + expiration. Returns user_id or raises GmailError."""
    if not state or '.' not in state:
        raise GmailError('Invalid OAuth state')
    parts = state.split('.', 1)
    payload_b64, sig = parts[0], parts[1]
    expected = hmac.new(_state_secret(), payload_b64.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise GmailError('Invalid OAuth state (signature mismatch)')
    try:
        padded = payload_b64 + '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        raise GmailError('Invalid OAuth state (payload malformed)')
    if time.time() - payload.get('ts', 0) > STATE_TTL_SECONDS:
        raise GmailError('OAuth state expired; please try again')
    user_id = payload.get('uid')
    if not user_id:
        raise GmailError('Invalid OAuth state (no user)')
    return user_id


# ============================================================================
# OAUTH URL + TOKEN EXCHANGE
# ============================================================================

def build_oauth_url(user_id: str) -> str:
    if not env.gmail_configured():
        raise GmailError('Gmail is not configured on this deployment')
    params = {
        'client_id':     env.GOOGLE_CLIENT_ID,
        'redirect_uri':  REDIRECT_URI,
        'response_type': 'code',
        'scope':         SCOPES,
        'access_type':   'offline',   # required for refresh_token
        'prompt':        'consent',   # force refresh_token even on re-auth
        'state':         encode_state(user_id),
    }
    return AUTH_URL + '?' + urllib.parse.urlencode(params)


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(
        url, data=body, method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        log.exception('Google token endpoint returned %s', e.code)
        raise GmailError('Google rejected the OAuth request')
    except Exception:
        log.exception('Google token endpoint failed')
        raise GmailError('Could not reach Google to complete sign-in')


def exchange_code_for_tokens(code: str) -> dict:
    """Returns dict with refresh_token, access_token, email."""
    if not env.gmail_configured():
        raise GmailError('Gmail is not configured on this deployment')
    tokens = _post_form(TOKEN_URL, {
        'client_id':     env.GOOGLE_CLIENT_ID,
        'client_secret': env.GOOGLE_CLIENT_SECRET,
        'code':          code,
        'redirect_uri':  REDIRECT_URI,
        'grant_type':    'authorization_code',
    })
    refresh_token = tokens.get('refresh_token')
    access_token = tokens.get('access_token')
    if not refresh_token or not access_token:
        log.error('token exchange response missing tokens: %s', tokens)
        raise GmailError('Google did not return a refresh token (try re-connecting)')
    email_addr = _fetch_userinfo_email(access_token)
    return {
        'refresh_token': refresh_token,
        'access_token':  access_token,
        'email':         email_addr,
    }


def _fetch_userinfo_email(access_token: str) -> str:
    req = urllib.request.Request(
        USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        log.exception('userinfo fetch failed')
        raise GmailError('Could not read Google account email')
    email_addr = data.get('email')
    if not email_addr:
        raise GmailError('Google account has no email')
    return email_addr


def refresh_access_token(refresh_token: str) -> str:
    if not env.gmail_configured():
        raise GmailError('Gmail is not configured on this deployment')
    tokens = _post_form(TOKEN_URL, {
        'client_id':     env.GOOGLE_CLIENT_ID,
        'client_secret': env.GOOGLE_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type':    'refresh_token',
    })
    access_token = tokens.get('access_token')
    if not access_token:
        raise GmailError('Google refresh returned no access token; please re-connect Gmail')
    return access_token


# ============================================================================
# SEND
# ============================================================================

def send(access_token: str, from_email: str, to: str, subject: str, body: str) -> str:
    """Send a plain-text email via Gmail API. Returns the Gmail message id."""
    msg = email.mime.text.MIMEText(body, _charset='utf-8')
    msg['From']    = from_email
    msg['To']      = to
    msg['Subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii').rstrip('=')

    req = urllib.request.Request(
        GMAIL_SEND_URL,
        data=json.dumps({'raw': raw}).encode('utf-8'),
        method='POST',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type':  'application/json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        log.exception('Gmail send returned %s', e.code)
        # Common causes: token revoked, quota, malformed message
        raise GmailError('Gmail rejected the send; you may need to re-connect Gmail')
    except Exception:
        log.exception('Gmail send failed')
        raise GmailError('Could not reach Gmail')
    return result.get('id', '')
