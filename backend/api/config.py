"""
Configuration validation API endpoints for MultiFetch v2.
"""

from flask import Blueprint, request, jsonify
from groq import Groq

config_bp = Blueprint("config", __name__)


def validate_api_key(api_key: str, test_connection: bool = False) -> dict:
    """
    Validate Groq API key.

    Args:
        api_key: The API key to validate
        test_connection: If True, make a test API call to verify the key works

    Returns:
        dict with validation results
    """
    result = {
        "valid": False,
        "error": None,
    }

    if not api_key:
        result["error"] = "API key is required"
        return result

    if not api_key.startswith("gsk_"):
        result["error"] = "Invalid API key format (should start with 'gsk_')"
        return result

    if len(api_key) < 20:
        result["error"] = "API key appears to be too short"
        return result

    # Optionally test the connection
    if test_connection:
        try:
            client = Groq(api_key=api_key)
            # Make a minimal API call to verify the key works
            client.models.list()
            result["valid"] = True
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid" in error_msg.lower():
                result["error"] = "Invalid API key"
            elif "rate" in error_msg.lower():
                # Rate limited but key is valid
                result["valid"] = True
            else:
                result["error"] = f"API error: {error_msg}"
    else:
        # Just format validation
        result["valid"] = True

    return result


def validate_cookies_content(content: str) -> dict:
    """
    Validate cookies file content (Netscape HTTP Cookie File format).

    Args:
        content: The cookies file content

    Returns:
        dict with validation results
    """
    result = {
        "valid": False,
        "cookie_count": 0,
        "domains": [],
        "error": None,
    }

    if not content:
        result["error"] = "Cookies content is empty"
        return result

    lines = content.strip().split("\n")
    valid_cookies = []
    domains = set()

    for line in lines:
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Netscape format: domain, flag, path, secure, expiry, name, value
        parts = line.split("\t")
        if len(parts) >= 7:
            valid_cookies.append(parts)
            domains.add(parts[0].lstrip("."))

    if not valid_cookies:
        result["error"] = "No valid cookies found (expected Netscape format)"
        return result

    result["valid"] = True
    result["cookie_count"] = len(valid_cookies)
    result["domains"] = sorted(domains)

    # Check for platform-specific cookies
    platform_cookies = {
        "instagram": ["sessionid", "csrftoken", "ds_user_id"],
        "tiktok": ["sessionid", "tt_webid"],
        "youtube": ["SAPISID", "HSID", "SSID"],
    }

    result["platforms"] = {}
    cookie_names = [c[5] for c in valid_cookies if len(c) > 5]

    for platform, required in platform_cookies.items():
        found = [name for name in required if name in cookie_names]
        if found:
            result["platforms"][platform] = {
                "detected": True,
                "cookies_found": found,
            }

    return result


@config_bp.route("/validate", methods=["POST"])
def validate():
    """
    Validate configuration (API key and/or cookies).

    Request body:
        {
            "api_key": "gsk_...",
            "test_connection": false,
            "cookies": "# Netscape HTTP Cookie File\n..."
        }

    Response:
        {
            "api_key": { validation result },
            "cookies": { validation result }
        }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    response = {}

    # Validate API key if provided
    if "api_key" in data:
        test_connection = data.get("test_connection", False)
        response["api_key"] = validate_api_key(data["api_key"], test_connection)

    # Validate cookies if provided
    if "cookies" in data:
        response["cookies"] = validate_cookies_content(data["cookies"])

    if not response:
        return jsonify({"error": "Request must include 'api_key' or 'cookies'"}), 400

    return jsonify(response)
