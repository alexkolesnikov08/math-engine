"""API tests using TestClient (no live server)."""

from __future__ import annotations

# ruff: noqa: S101 (pytest asserts are idiomatic; mirrors tests/test_engine.py style)

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_serves_html():
    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "textarea" in resp.text
    assert "/solve" in resp.text
    assert "katex" in resp.text.lower()


def test_solve_quadratic_returns_legacy_four_steps():
    resp = client.post("/solve", json={"latex": r"x^2 - 5x + 6 = 0"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "v2"
    assert data["input"] == r"x^2 - 5x + 6 = 0"
    assert data["error"] is None
    # Default (verbose=false) is the legacy contract: exactly 4 steps.
    assert len(data["steps"]) == 4
    assert [s["kind"] for s in data["steps"]] == [
        "input",
        "simplified",
        "symbolic",
        "numeric",
    ]
    assert all(s["title"].strip() for s in data["steps"])
    assert all(set(s.keys()) == {"kind", "title", "latex"} for s in data["steps"])


def test_solve_verbose_returns_full_steps():
    resp = client.post(
        "/solve", json={"latex": r"x^2 - 5x + 6 = 0", "verbose": True}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "v2"
    assert data["error"] is None
    assert len(data["steps"]) == 10
    kinds = [s["kind"] for s in data["steps"]]
    assert "derivation" in kinds
    assert "verification" in kinds


def test_solve_precision_changes_numeric():
    low = client.post("/solve", json={"latex": r"x^2 - 2 = 0", "precision": 3})
    high = client.post("/solve", json={"latex": r"x^2 - 2 = 0", "precision": 15})

    assert low.status_code == 200
    assert high.status_code == 200
    assert low.json()["error"] is None
    assert high.json()["error"] is None
    low_numeric = next(
        s["latex"] for s in low.json()["steps"] if s["kind"] == "numeric"
    )
    high_numeric = next(
        s["latex"] for s in high.json()["steps"] if s["kind"] == "numeric"
    )
    assert low_numeric != high_numeric
    assert "1.41" in low_numeric
    assert "1.4142" in high_numeric


def test_solve_precision_out_of_range_returns_422():
    assert (
        client.post("/solve", json={"latex": "x = 1", "precision": 0}).status_code
        == 422
    )
    assert (
        client.post("/solve", json={"latex": "x = 1", "precision": 51}).status_code
        == 422
    )


def test_solve_empty_latex_returns_422():
    resp = client.post("/solve", json={"latex": ""})

    assert resp.status_code == 422


def test_solve_whitespace_latex_returns_422():
    resp = client.post("/solve", json={"latex": "   "})

    assert resp.status_code == 422


def test_solve_invalid_input_returns_200_with_error():
    resp = client.post("/solve", json={"latex": "this is not a valid latex equation"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert data["version"] == "v2"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["kind"] == "error"
