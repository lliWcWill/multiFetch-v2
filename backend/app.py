"""
MultiFetch v2 - Flask Backend
Hot reload: make dev (or flask run --debug)
"""

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()


def create_app():
    """Application factory pattern."""
    app = Flask(__name__)

    # CORS for frontend
    CORS(app, origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")])

    # Health check
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "version": "2.0.0"})

    # Register blueprints
    from api.urls import urls_bp

    app.register_blueprint(urls_bp, url_prefix="/api/urls")

    # TODO: Register additional blueprints
    # from api.config import config_bp
    # from api.jobs import jobs_bp
    # from api.tiktok import tiktok_bp
    # app.register_blueprint(config_bp, url_prefix="/api/config")
    # app.register_blueprint(jobs_bp, url_prefix="/api/jobs")
    # app.register_blueprint(tiktok_bp, url_prefix="/api/tiktok")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
