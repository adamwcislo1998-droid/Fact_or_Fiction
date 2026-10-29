"""HTTP-level tests for the Flask API.

These tests use Flask's in-process test client, so no real network port is opened.
They verify the public contract rather than private implementation details.
"""

from app import create_app


# The extension relies on a successful health response before analysis.
def test_health_endpoint():
    client = create_app(testing=True).test_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


# Submit a realistic payload and check key fields/ranges rather than an exact
# score, making the test robust to small internal weighting refinements.
def test_analyse_endpoint_returns_structured_result():
    client = create_app(testing=True).test_client()
    response = client.post(
        "/api/v1/analyse",
        json={
            "url": "https://www.reddit.com/r/test/comments/abc/test/",
            "title": "Example title",
            "body": "According to a report, this estimate may change.",
            "comments": [{"text": "Can you provide the source?"}],
        },
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert -1 <= data["score"] <= 1
    assert data["comment_analysis"]["captured_count"] == 1
    assert isinstance(data["indicators"], list)


# Comments alone are insufficient because the tool is intended to analyse the
# open Reddit post. The API must return a client error instead of crashing.
def test_analyse_endpoint_rejects_missing_post_text():
    client = create_app(testing=True).test_client()
    response = client.post("/api/v1/analyse", json={"comments": ["Only a comment"]})
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
