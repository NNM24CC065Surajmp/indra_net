import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend
import main
import phyphox


@pytest.fixture(autouse=True)
def reset_backend_state():
    """Reset shared backend state and stop background threads around every test."""
    backend.stop_background_workers()
    backend.app.config["TESTING"] = True

    with backend._devices_lock:
        backend.latest_device_count = 0

    with backend._camera_lock:
        backend.current_crowd_count = 0
        backend.camera_last_updated = None
        backend.camera_stale = True

    with backend._motion_lock:
        backend.prev_mag = 0
        backend.history.clear()
        backend.latest_norm_instability = 0.0
        backend.motion_last_updated = None
        backend.motion_stale = True

    yield

    backend.stop_background_workers()


def test_home_and_update_devices_api():
    client = backend.app.test_client()

    res = client.get("/")
    assert res.status_code == 200
    assert res.data == b"Backend running!"

    post_res = client.post("/update_devices", json={"device_count": 12})
    assert post_res.status_code == 200
    assert post_res.get_json() == {"status": "ok", "received_device_count": 12}

    bad_res = client.post("/update_devices", data="not-json", content_type="text/plain")
    assert bad_res.status_code == 400


def test_get_data_does_not_poll_camera_or_phyphox_directly(monkeypatch):
    cam_calls = 0
    phy_calls = 0

    def fail_cam():
        nonlocal cam_calls
        cam_calls += 1
        return {"total": 99}

    def fail_phy():
        nonlocal phy_calls
        phy_calls += 1
        return (5.0, 0.0, 0.0)

    monkeypatch.setattr(backend, "_fetch_camera_counts", fail_cam)
    monkeypatch.setattr(phyphox, "fetch_data", fail_phy)

    with backend._camera_lock:
        backend.current_crowd_count = 20
        backend.camera_last_updated = 1000.0
        backend.camera_stale = False

    with backend._motion_lock:
        backend.latest_norm_instability = 0.5
        backend.motion_last_updated = 1001.0
        backend.motion_stale = False

    client = backend.app.test_client()
    for _ in range(5):
        res = client.get("/data?area=100")
        assert res.status_code == 200
        payload = res.get_json()
        assert payload["crowd_count"] == 20
        assert payload["device_count"] == 0
        assert payload["crowd_density"] == 0.2
        assert payload["area"] == 100.0
        assert payload["instability"] == 5.0
        assert payload["risk"] == 0.5  # 0.5*(20/100) + 0.2*0.5 + 0.3 boost = 0.5
        assert payload["alert"] == "MEDIUM"
        assert payload["camera_updated_at"] == 1000.0
        assert payload["camera_stale"] is False
        assert payload["motion_updated_at"] == 1001.0
        assert payload["motion_stale"] is False

    assert cam_calls == 0
    assert phy_calls == 0


def test_camera_refresh_keeps_last_value_and_timestamp_on_failure(monkeypatch):
    monkeypatch.setattr(backend, "_fetch_camera_counts", lambda: {"total": 34})
    count = backend.refresh_camera_count()
    assert count == 34

    with backend._camera_lock:
        first_ts = backend.camera_last_updated
        assert first_ts is not None
        assert backend.camera_stale is False

    def raise_offline():
        raise ConnectionError("camera offline")

    monkeypatch.setattr(backend, "_fetch_camera_counts", raise_offline)
    count_after_fail = backend.refresh_camera_count()
    assert count_after_fail == 34

    client = backend.app.test_client()
    payload = client.get("/data").get_json()
    assert payload["crowd_count"] == 34
    assert payload["camera_updated_at"] == first_ts
    assert payload["camera_stale"] is True


def test_motion_refresh_keeps_last_value_and_flags_stale_when_phyphox_offline(monkeypatch):
    # Online sample produces non-zero instability
    monkeypatch.setattr(phyphox, "fetch_data", lambda timeout=2: (10.0, 0.0, 0.0))
    norm = backend.refresh_motion_state()
    assert norm > 0

    with backend._motion_lock:
        saved_norm = backend.latest_norm_instability
        saved_ts = backend.motion_last_updated
        saved_history = list(backend.history)
        assert saved_ts is not None
        assert backend.motion_stale is False

    # Phyphox goes offline: last value & history must be preserved, flagged stale
    def offline_phyphox(timeout=2):
        raise TimeoutError("Phyphox timed out")

    monkeypatch.setattr(phyphox, "fetch_data", offline_phyphox)
    norm_after_offline = backend.refresh_motion_state()
    assert norm_after_offline == saved_norm

    with backend._motion_lock:
        assert backend.history == saved_history

    client = backend.app.test_client()
    payload = client.get("/data").get_json()
    assert payload["instability"] == round(saved_norm * 10, 2)
    assert payload["motion_updated_at"] == saved_ts
    assert payload["motion_stale"] is True

    # Recover when Phyphox comes back online
    monkeypatch.setattr(phyphox, "fetch_data", lambda timeout=2: (10.0, 0.0, 0.0))
    backend.refresh_motion_state()
    payload_recovered = client.get("/data").get_json()
    assert payload_recovered["motion_stale"] is False
    assert payload_recovered["motion_updated_at"] >= saved_ts


def test_get_data_is_non_blocking_while_phyphox_thread_is_blocked(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_phyphox(timeout=2):
        started.set()
        release.wait(timeout=2.0)
        return (0.0, 0.0, 0.0)

    monkeypatch.setattr(phyphox, "fetch_data", slow_phyphox)
    monkeypatch.setattr(backend, "_fetch_camera_counts", lambda: {"total": 5})
    monkeypatch.setattr(backend, "CAMERA_POLL_INTERVAL", 0.02)
    monkeypatch.setattr(backend, "MOTION_POLL_INTERVAL", 0.02)

    backend.start_background_workers()
    assert started.wait(timeout=1.0)

    client = backend.app.test_client()
    t0 = time.perf_counter()
    res = client.get("/data")
    elapsed = time.perf_counter() - t0

    release.set()
    backend.stop_background_workers()

    assert res.status_code == 200
    assert elapsed < 0.1


def test_background_threads_refresh_camera_and_motion(monkeypatch):
    cam_seq = iter([{"total": 3}, {"total": 7}, {"total": 7}])
    phy_seq = iter([(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (5.0, 0.0, 0.0)])

    monkeypatch.setattr(backend, "_fetch_camera_counts", lambda: next(cam_seq, {"total": 7}))
    monkeypatch.setattr(phyphox, "fetch_data", lambda timeout=2: next(phy_seq, (5.0, 0.0, 0.0)))
    monkeypatch.setattr(backend, "CAMERA_POLL_INTERVAL", 0.02)
    monkeypatch.setattr(backend, "MOTION_POLL_INTERVAL", 0.02)

    backend.start_background_workers()
    time.sleep(0.1)
    backend.stop_background_workers()

    client = backend.app.test_client()
    payload = client.get("/data").get_json()
    assert payload["crowd_count"] == 7
    assert payload["camera_stale"] is False
    assert payload["camera_updated_at"] is not None
    assert payload["motion_stale"] is False
    assert payload["motion_updated_at"] is not None
    assert payload["instability"] > 0


def test_phyphox_get_data_still_returns_zero_tuple_on_error(monkeypatch):
    def fail_fetch(timeout=2):
        raise RuntimeError("offline")

    monkeypatch.setattr(phyphox, "fetch_data", fail_fetch)
    assert phyphox.get_data() == (0, 0, 0)


def test_main_stability_and_instability_not_inverted():
    assert main.compute_stability_score(0) == 100
    assert main.compute_stability_score(10) == 0
    assert main.compute_stability_score(3.5) == 65
    assert main.compute_stability_score(-1) == 100
    assert main.compute_stability_score(15) == 0

    assert main.compute_motion_index(0) == 0.0
    assert main.compute_motion_index(3.567) == 3.57
    assert main.compute_motion_index(12) == 10.0

    # Higher instability must strictly mean lower stability
    assert main.compute_stability_score(8) < main.compute_stability_score(2)


def test_render_dashboard_displays_non_inverted_stability_and_stale_flag(monkeypatch):
    class StopRerun(Exception):
        pass

    class DummyColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    rendered_markdown = []

    class DummyStreamlit:
        def set_page_config(self, **kwargs):
            pass

        def markdown(self, text, **kwargs):
            rendered_markdown.append(text)

        def columns(self, spec, **kwargs):
            count = spec if isinstance(spec, int) else len(spec)
            return [DummyColumn() for _ in range(count)]

        def selectbox(self, label, options, **kwargs):
            return options[0]

        def rerun(self):
            raise StopRerun()

    class DummyResponse:
        def json(self):
            return {
                "crowd_count": 10,
                "device_count": 4,
                "instability": 3.5,
                "risk": 0.25,
                "alert": "LOW",
                "motion_stale": True,
            }

    class DummyRequests:
        class exceptions:
            class ConnectionError(Exception):
                pass

        def get(self, url, timeout=5):
            return DummyResponse()

    monkeypatch.setattr(main, "st", DummyStreamlit())
    monkeypatch.setattr(main, "requests", DummyRequests())
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    with pytest.raises(StopRerun):
        main.render_dashboard()

    html = "\n".join(rendered_markdown)
    assert "65/100" in html
    assert "Stability Score (Stale)" in html
    assert "INSTABILITY INDEX" in html
    assert ">3.5<" in html

