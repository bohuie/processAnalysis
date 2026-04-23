import os
import time
import subprocess
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = os.getenv("DOCKER_COMPOSE", "docker-compose")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
RUN_DOCKER_TEST = os.getenv("RUN_DOCKER_TEST", "0") == "1"

RUN_ENDPOINT = f"{API_BASE_URL}/run"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
COUNT_ENDPOINT = f"{API_BASE_URL}/graphs/count"
LIST_ENDPOINT = f"{API_BASE_URL}/graphs/list"


def _compose(*args: str, timeout: int = 300):
    return subprocess.run([COMPOSE, *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=timeout)


def _wait_for_health(timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(HEALTH_ENDPOINT, timeout=5)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False


@pytest.mark.skipif(not RUN_DOCKER_TEST, reason="Set RUN_DOCKER_TEST=1 to run dockerized API test")
def test_docker_compose_pipeline():
    # Bring up the stack
    _compose("up", "-d", "--build")

    # Wait for API health
    assert _wait_for_health(), "API health endpoint did not become ready"

    # Trigger pipeline
    resp = requests.post(RUN_ENDPOINT, timeout=600)
    assert resp.status_code == 200, f"Run endpoint failed: {resp.text}"

    # Check graphs count
    resp = requests.get(COUNT_ENDPOINT, timeout=20)
    assert resp.status_code == 200, f"Count endpoint failed: {resp.text}"
    cnt = resp.json().get("count")
    assert cnt is not None and cnt >= 0

    # List a few graphs
    resp = requests.get(LIST_ENDPOINT, params={"limit": 3}, timeout=20)
    assert resp.status_code == 200, f"List endpoint failed: {resp.text}"
    items = resp.json().get("items", [])
    assert isinstance(items, list)

    # Tear down stack
    _compose("down", "-v")
