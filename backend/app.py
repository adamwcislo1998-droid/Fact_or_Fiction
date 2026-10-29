"""Flask server used by the browser extension.

This module is the HTTP entry point for the Python backend.  It does not perform
text analysis itself.  Its responsibilities are to create the Flask app, accept
JSON from the extension, validate the request through ``AnalysisInput``, pass the
validated data to ``CredibilityEngine``, and return a JSON response.
"""

# Flask creates the local HTTP service. ``jsonify`` produces valid JSON
# responses and ``request`` exposes the request currently being processed.
from flask import Flask, jsonify, request
# The extension has a chrome-extension:// origin while the server uses
# http://127.0.0.1:5000. CORS adds the response headers that allow the browser
# to permit communication between those two origins.
from flask_cors import CORS

# Centralised configuration keeps host, port, limits and optional-model settings
# out of the route functions.
import config
# AnalysisInput validates incoming data; CredibilityEngine calculates the
# result; InputValidationError identifies an expected client-input problem.
from credibility import AnalysisInput, CredibilityEngine, InputValidationError


# Application-factory pattern: tests can create an isolated Flask application
# with ``testing=True`` while normal execution uses the same construction path.
def create_app(testing=False):
    # ``__name__`` tells Flask which Python module owns the application.
    app = Flask(__name__)
    # Flask changes some error-handling behaviour in testing mode.
    app.config["TESTING"] = testing
    # Reject complete HTTP request bodies above roughly 1 MB before expensive
    # analysis begins. Individual fields are limited again during validation.
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000

    # The extension runs in the browser and sends requests to this local server.
    CORS(app)

    # Create one reusable engine for this Flask application. Reusing it avoids
    # repeatedly rebuilding VADER and, when enabled, the transformer pipeline.
    engine = CredibilityEngine(
        # Tests always use lightweight deterministic mode and never download a
        # transformer model. Normal runs follow the environment setting.
        enable_transformer=False if testing else config.ENABLE_TRANSFORMER,
        transformer_model=config.TRANSFORMER_MODEL,
    )

    # Both routes call the same health function. The versioned route is used by
    # the extension; the shorter route is convenient for manual checking.
    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        # A health check proves that Flask and the engine were created. It does
        # not analyse any Reddit content.
        return jsonify(
            ok=True,
            status="healthy",
            service="fact-or-fiction-backend",
            engine_version=engine.VERSION,
            transformer_enabled=engine.transformer.enabled,
        )

    # POST is used because the extension submits a potentially large JSON body
    # for processing rather than merely retrieving a fixed resource.
    @app.post("/analyse")
    @app.post("/api/v1/analyse")
    def analyse():
        # Flask checks the Content-Type header before attempting JSON parsing.
        if not request.is_json:
            return error_response("Content-Type must be application/json.", 415)

        # ``silent=True`` returns None for malformed JSON instead of replacing
        # the project's structured error response with Flask's default page.
        payload = request.get_json(silent=True)
        if payload is None:
            return error_response("The JSON request body could not be parsed.", 400)

        try:
            # Convert untrusted JSON into a bounded, predictable data model.
            analysis_input = AnalysisInput.from_payload(
                payload,
                max_comments=config.MAX_COMMENTS,
                max_text_chars=config.MAX_TEXT_CHARS,
            )
            # The engine returns an ordinary dictionary; jsonify serialises it
            # and sets the application/json response type.
            return jsonify(engine.analyse(analysis_input))
        except InputValidationError as exc:
            return error_response(str(exc), 400)

    # Flask raises 413 automatically when MAX_CONTENT_LENGTH is exceeded.
    @app.errorhandler(413)
    def request_too_large(_error):
        return error_response("The analysis request is too large.", 413)

    # Final safety net for unexpected failures. Expected validation errors are
    # handled above and therefore do not reach this broad handler.
    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception("Unexpected analysis error")
        if app.testing:
            raise exc
        return error_response("The backend encountered an unexpected error.", 500)

    return app


# Give every error the same JSON shape so the JavaScript client can extract a
# message without special cases for each route.
def error_response(message, status_code):
    return jsonify(ok=False, error={"message": message, "status": status_code}), status_code


# Module-level application supports ``python app.py`` and WSGI-style imports.
app = create_app()

# Only start Flask's development server when this file is executed directly;
# importing it from pytest must not start a blocking server process.
if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
