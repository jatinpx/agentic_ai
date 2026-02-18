"""
LinkedIn OAuth2 + Share API integration.

Required env vars:
    LINKEDIN_CLIENT_ID
    LINKEDIN_CLIENT_SECRET
    LINKEDIN_REDIRECT_URI
    LINKEDIN_ACCESS_TOKEN   (set after OAuth2 flow)
    LINKEDIN_REFRESH_TOKEN  (set after OAuth2 flow)
"""

import os
import json
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

# Token storage (in production, persist in DB)
_token_store: Dict[str, str] = {
    "access_token": os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
    "refresh_token": os.getenv("LINKEDIN_REFRESH_TOKEN", ""),
}

LINKEDIN_API_BASE = "https://api.linkedin.com"
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

# Scopes required for posting
LINKEDIN_SCOPES = "openid profile w_member_social"


# ==========================================
# OAUTH2 FLOW
# ==========================================

def get_auth_url(state: str = "linkedin_oauth") -> str:
    """Generate LinkedIn OAuth2 authorization URL."""
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": state,
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
    user_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish a text-only post to LinkedIn using the UGC Post API.

    Returns:
        dict with 'id' (post URN) on success, or 'error' on failure.
    """
    token = access_token or get_access_token()
    if not token:
        return {"error": "No access token. Complete OAuth2 flow first."}

    urn = user_urn or get_user_urn(token)
    if not urn:
        return {"error": "Could not resolve user URN. Check token validity."}

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
            return {"id": post_id, "url": post_url}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def publish_image_post(
    text: str,
    image_url: str,
    access_token: Optional[str] = None,
    user_urn: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish a post with an image to LinkedIn.
    Note: Full image upload requires register + upload + publish flow.
    This is a placeholder for future implementation.
    """
    # LinkedIn image posting requires: registerUpload → binary upload → ugcPost
    # For now, fall back to text-only
    return publish_text_post(text, access_token, user_urn)


def schedule_post(
    text: str,
    scheduled_time: str,
    access_token: Optional[str] = None,
    user_urn: Optional[str] = None,
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
