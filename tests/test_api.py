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


def test_solve_quadratic_returns_four_steps():
    resp = client.post("/solve", json={"latex": r"x^2 - 5x + 6 = 0"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["input"] == r"x^2 - 5x + 6 = 0"
    assert data["error"] is None
    # Honest derivation steps (step_builders) expand the legacy 4.
    assert len(data["steps"]) >= 4
    kinds = [s["kind"] for s in data["steps"]]
    assert kinds[0] == "input"
    assert "symbolic" in kinds and "numeric" in kinds
    assert "derivation" in kinds or "verification" in kinds
    assert all(s["title"].strip() for s in data["steps"])
    assert all(set(s.keys()) == {"kind", "title", "latex"} for s in data["steps"])


def test_solve_precision_passthrough():
    resp = client.post("/solve", json={"latex": r"x^2 - 5x + 6 = 0", "precision": 10})

    assert resp.status_code == 200
    assert resp.json()["error"] is None
    assert len(resp.json()["steps"]) >= 4


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
    assert len(data["steps"]) == 1
    assert data["steps"][0]["kind"] == "error"
