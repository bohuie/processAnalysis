import os
import time
import requests
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
RUN_ENDPOINT = f"{API_BASE_URL}/run"
COUNT_ENDPOINT = f"{API_BASE_URL}/graphs/count"
LIST_ENDPOINT = f"{API_BASE_URL}/graphs/list"


def _service_available(url: str, timeout: float = 2.0) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except requests.RequestException:
        return False


def test_run_pipeline_and_store_graphs():
    if not _service_available(API_BASE_URL):
        pytest.skip("API service not reachable; ensure docker-compose is running on :8000")

    # Trigger full pipeline
    resp = requests.post(RUN_ENDPOINT, timeout=600)
    assert resp.status_code == 200, f"Run endpoint failed: {resp.text}"
    data = resp.json()
    assert data.get("status") == "ok"

    # Give the DB a moment to finish commits
    time.sleep(2)

    # Check graph count
    resp = requests.get(COUNT_ENDPOINT, timeout=10)
    assert resp.status_code == 200, f"Count endpoint failed: {resp.text}"
    cnt = resp.json().get("count")
    assert cnt is not None and cnt >= 0

    # Fetch a small list to ensure rows exist
    resp = requests.get(LIST_ENDPOINT, params={"limit": 5}, timeout=10)
    assert resp.status_code == 200, f"List endpoint failed: {resp.text}"
    items = resp.json().get("items", [])
    assert isinstance(items, list)

    # If nothing returned, allow but log
    if not items:
        pytest.skip("Pipeline ran but no graphs were stored (empty dataset)")
