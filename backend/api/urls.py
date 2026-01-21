"""
URL validation API endpoints for MultiFetch v2.
"""

from flask import Blueprint, request, jsonify

from services.platform_detector import validate_url, validate_urls_batch

urls_bp = Blueprint("urls", __name__)


@urls_bp.route("/validate", methods=["POST"])
def validate():
    """
    Validate one or more URLs.

    Request body:
        {"url": "https://..."} or {"urls": ["https://...", ...]}

    Response:
        Single URL: validation result dict
        Multiple URLs: {"results": [validation result dicts]}
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    # Single URL
    if "url" in data:
        result = validate_url(data["url"])
        return jsonify(result)

    # Multiple URLs
    if "urls" in data:
        if not isinstance(data["urls"], list):
            return jsonify({"error": "urls must be an array"}), 400
        if len(data["urls"]) > 100:
            return jsonify({"error": "Maximum 100 URLs per request"}), 400
        results = validate_urls_batch(data["urls"])
        return jsonify({"results": results})

    return jsonify({"error": "Request must include 'url' or 'urls'"}), 400
