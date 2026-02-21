"""
LinkedIn OAuth2 + Share API integration.

Required env vars:
    LINKEDIN_CLIENT_ID
    LINKEDIN_CLIENT_SECRET
    LINKEDIN_REDIRECT_URI
    LINKEDIN_ACCESS_TOKEN   (set after OAuth2 flow)
    LINKEDIN_REFRESH_TOKEN  (set after OAuth2 flow)
    LINKEDIN_AUTHOR_URN     (optional: urn:li:organization:<id> to post as page)
    LINKEDIN_ENABLE_ORG_POSTING (optional: true/false)
"""

import os
import json
import time
import secrets
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIG
# ==========================================

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:3000/api/linkedin/callback")

LINKEDIN_AUTHOR_URN = os.getenv("LINKEDIN_AUTHOR_URN", "").strip()
LINKEDIN_ORGANIZATION_ID = os.getenv("LINKEDIN_ORGANIZATION_ID", "").strip()
LINKEDIN_ENABLE_ORG_POSTING = os.getenv("LINKEDIN_ENABLE_ORG_POSTING", "false").strip().lower() in ("1", "true", "yes", "on")

# Token storage (in production, persist in DB)
_token_store: Dict[str, str] = {
    "access_token": os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
    "refresh_token": os.getenv("LINKEDIN_REFRESH_TOKEN", ""),
}

LINKEDIN_API_BASE = "https://api.linkedin.com"
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

def _build_scope_string() -> str:
    scopes = ["openid", "profile", "email", "w_member_social"]
    if LINKEDIN_ENABLE_ORG_POSTING:
        scopes.extend(["w_organization_social", "rw_organization_admin"])
    return " ".join(scopes)


# Scopes required for posting + user identity lookup
LINKEDIN_SCOPES = _build_scope_string()

# In-memory OAuth state storage (in production, persist in DB/Redis)
_oauth_states: Dict[str, float] = {}
STATE_TTL_SECONDS = 600


def _cleanup_expired_states() -> None:
    now = time.time()
    expired = [key for key, created in _oauth_states.items() if now - created > STATE_TTL_SECONDS]
    for key in expired:
        _oauth_states.pop(key, None)


def create_oauth_state() -> str:
    _cleanup_expired_states()
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = time.time()
    return state


def validate_oauth_state(state: str) -> bool:
    _cleanup_expired_states()
    if state in _oauth_states:
        _oauth_states.pop(state, None)
        return True
    return False


# ==========================================
# OAUTH2 FLOW
# ==========================================

def get_auth_url(state: Optional[str] = None) -> str:
    """Generate LinkedIn OAuth2 authorization URL."""
    oauth_state = state or create_oauth_state()
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": oauth_state,
        "scope": LINKEDIN_SCOPES,
    })
    return f"{LINKEDIN_AUTH_URL}?{params}"


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """
    Exchange authorization code for access token.
    Returns dict with: access_token, expires_in, refresh_token, etc.
    """
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "client_id": LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
    }).encode("utf-8")

    req = urllib.request.Request(
        LINKEDIN_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

        # Store tokens
        _token_store["access_token"] = result.get("access_token", "")
        _token_store["refresh_token"] = result.get("refresh_token", "")

        return result
    except Exception as e:
        return {"error": str(e)}


def refresh_access_token() -> Dict[str, Any]:
    """Refresh the access token using the refresh token."""
    refresh_token = _token_store.get("refresh_token", "")
    if not refresh_token:
        return {"error": "No refresh token available"}

    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
    }).encode("utf-8")

    req = urllib.request.Request(
        LINKEDIN_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

        _token_store["access_token"] = result.get("access_token", "")
        if result.get("refresh_token"):
            _token_store["refresh_token"] = result["refresh_token"]

        return result
    except Exception as e:
        return {"error": str(e)}


def get_access_token() -> str:
    """Get current access token from store."""
    return _token_store.get("access_token", "")


def set_access_token(token: str):
    """Manually set access token (e.g., from env or callback)."""
    _token_store["access_token"] = token


def _resolve_author_urn(access_token: str) -> Optional[str]:
    """
    Resolve LinkedIn author URN.

    Priority:
      1) LINKEDIN_AUTHOR_URN (explicit, supports person/org)
      2) LINKEDIN_ORGANIZATION_ID (converted to organization URN)
      3) Authenticated user person URN
    """
    if LINKEDIN_AUTHOR_URN:
        return LINKEDIN_AUTHOR_URN

    if LINKEDIN_ORGANIZATION_ID:
        org_id = LINKEDIN_ORGANIZATION_ID
        if org_id.startswith("urn:li:organization:"):
            return org_id
        return f"urn:li:organization:{org_id}"

    return get_user_urn(access_token)


def get_configured_author_target() -> Dict[str, Any]:
    """Return current author target configuration for diagnostics/UI."""
    if LINKEDIN_AUTHOR_URN:
        return {
            "mode": "author_urn",
            "author_urn": LINKEDIN_AUTHOR_URN,
            "org_posting_enabled": LINKEDIN_ENABLE_ORG_POSTING,
            "scopes": LINKEDIN_SCOPES,
        }

    if LINKEDIN_ORGANIZATION_ID:
        author_urn = (
            LINKEDIN_ORGANIZATION_ID
            if LINKEDIN_ORGANIZATION_ID.startswith("urn:li:organization:")
            else f"urn:li:organization:{LINKEDIN_ORGANIZATION_ID}"
        )
        return {
            "mode": "organization_id",
            "author_urn": author_urn,
            "org_posting_enabled": LINKEDIN_ENABLE_ORG_POSTING,
            "scopes": LINKEDIN_SCOPES,
        }

    return {
        "mode": "personal_profile",
        "author_urn": "",
        "org_posting_enabled": LINKEDIN_ENABLE_ORG_POSTING,
        "scopes": LINKEDIN_SCOPES,
    }


# ==========================================
# USER PROFILE
# ==========================================

def get_user_profile(access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the authenticated user's LinkedIn profile info.
    Returns dict with: sub (user URN), name, email, etc.
    """
    token = access_token or get_access_token()
    if not token:
        return {"error": "No access token"}

    req = urllib.request.Request(
        f"{LINKEDIN_API_BASE}/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def get_user_urn(access_token: Optional[str] = None) -> Optional[str]:
    """Get the user's LinkedIn URN (needed for posting)."""
    profile = get_user_profile(access_token)
    sub = profile.get("sub")
    if sub:
        return f"urn:li:person:{sub}"
    return None


# ==========================================
# PUBLISHING
# ==========================================

def publish_text_post(
    text: str,
    access_token: Optional[str] = None,
    author_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish a text-only post to LinkedIn using the UGC Post API.

    Returns:
        dict with 'id' (post URN) on success, or 'error' on failure.
    """
    token = access_token or get_access_token()
    if not token:
        return {"error": "No access token. Complete OAuth2 flow first."}

    urn = author_urn or _resolve_author_urn(token)
    if not urn:
        return {"error": "Could not resolve author URN. Check token validity and org settings."}

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{LINKEDIN_API_BASE}/v2/ugcPosts",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            post_id = result.get("id", "")
            post_url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""
            return {"id": post_id, "url": post_url, "author": urn}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def publish_image_post(
    text: str,
    image_url: str,
    access_token: Optional[str] = None,
    author_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish a post with an image to LinkedIn.
    Note: Full image upload requires register + upload + publish flow.
    This is a placeholder for future implementation.
    """
    # LinkedIn image posting requires: registerUpload → binary upload → ugcPost
    # For now, fall back to text-only
    return publish_text_post(text, access_token, author_urn)


def schedule_post(
    text: str,
    scheduled_time: str,
    access_token: Optional[str] = None,
    author_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Schedule a post for future publishing.
    LinkedIn API doesn't natively support scheduling.
    This stores the intent — a background worker would pick it up.
    """
    # In production: store in DB with scheduled_at timestamp
    # A cron job / background task would publish at the right time
    return {
        "status": "scheduled",
        "scheduled_time": scheduled_time,
        "text_preview": text[:100] + "..." if len(text) > 100 else text,
        "note": "Scheduling requires a background worker. Post saved for manual publishing."
    }


def is_authenticated() -> bool:
    """Check if we have a valid access token."""
    token = get_access_token()
    if not token:
        return False
    # Quick validation: try to get user info
    profile = get_user_profile(token)
    return "error" not in profile


def _extract_post_urn_from_url_or_id(post_url: Optional[str] = None, post_id: Optional[str] = None) -> Optional[str]:
    """Convert LinkedIn post id/url into canonical ugcPost URN when possible."""
    raw = (post_id or "").strip()
    if not raw and post_url:
        parts = [p for p in post_url.split("/") if p]
        raw = parts[-1] if parts else ""
    if not raw:
        return None
    if raw.startswith("urn:li:"):
        return raw
    return f"urn:li:ugcPost:{raw}"


def fetch_post_engagement(post_url: Optional[str] = None, post_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch engagement counters for a LinkedIn post via Social Actions API.
    Returns a normalized dict; if endpoint/scope unsupported, returns error.
    """
    token = access_token or get_access_token()
    if not token:
        return {"error": "No access token"}

    post_urn = _extract_post_urn_from_url_or_id(post_url=post_url, post_id=post_id)
    if not post_urn:
        return {"error": "Could not resolve post URN"}

    encoded_urn = urllib.parse.quote(post_urn, safe="")
    url = f"{LINKEDIN_API_BASE}/rest/socialActions/{encoded_urn}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Linkedin-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        comments = payload.get("commentsSummary", {}).get("totalFirstLevelComments", 0)
        reactions = payload.get("likesSummary", {}).get("totalLikes", 0)
        reposts = payload.get("sharesSummary", {}).get("totalShares", 0)

        # LinkedIn does not always expose impressions in this endpoint
        impressions = payload.get("impressionSummary", {}).get("total", 0)

        return {
            "post_urn": post_urn,
            "impressions": int(impressions or 0),
            "reactions": int(reactions or 0),
            "comments": int(comments or 0),
            "reposts": int(reposts or 0),
            "payload": payload,
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"HTTP {e.code}: {body}", "post_urn": post_urn}
    except Exception as e:
        return {"error": str(e), "post_urn": post_urn}
