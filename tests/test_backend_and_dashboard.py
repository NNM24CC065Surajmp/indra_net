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

    with backend._profile_lock:
        backend.active_profile_name = "default"

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
        session_state = {}

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
                "profile": "default",
                "profile_label": "Default (current model)",
                "advice": "Normal monitoring.",
            }

    class DummyRequests:
        class exceptions:
            class ConnectionError(Exception):
                pass

        def get(self, url, timeout=5):
            return DummyResponse()

        def post(self, url, **kwargs):
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
    assert "DEFAULT (CURRENT MODEL)" in html
    assert "Normal monitoring." in html


def _legacy_calculate_risk(crowd_count, device_count, norm_instability):
    """The original hardcoded risk formula from backend.py."""
    risk = (
        0.5 * (crowd_count / 100) +
        0.3 * (device_count / 50) +
        0.2 * norm_instability
    )

    if norm_instability > 0.4:
        risk += 0.3
    if norm_instability > 0.7:
        risk += 0.6

    if risk > 0.7:
        alert = "HIGH"
    elif risk > 0.4:
        alert = "MEDIUM"
    else:
        alert = "LOW"

    return round(min(risk, 1), 2), alert


def test_default_profile_exact_parity_with_legacy_formula():
    """Verify default profile reproduces legacy formula exactly, including 0.4/0.7 boundaries."""
    test_cases = [
        # (crowd_count, device_count, norm_instability)
        (0, 0, 0.0),
        (10, 5, 0.1),
        (50, 25, 0.2),
        (20, 10, 0.3),
        # Exact risk boundary 0.4 (0.5 * 0.8 = 0.40, M <= 0.4 -> no boost)
        (80, 0, 0.0),
        # Just below risk boundary 0.4 (0.5 * 0.78 = 0.39)
        (78, 0, 0.0),
        # Just above risk boundary 0.4 (0.5 * 0.82 = 0.41)
        (82, 0, 0.0),
        # Exact motion spike threshold 0.4 (no boost: 0.5*0.4 + 0.3*0.2 + 0.2*0.4 = 0.34)
        (40, 10, 0.4),
        # Just above motion spike threshold 0.4 (+0.3 boost)
        (40, 10, 0.4001),
        (30, 15, 0.5),
        # Exact risk boundary 0.7 without spike (0.5*1.0 + 0.3*0.4 + 0.2*0.4 = 0.70)
        (100, 20, 0.4),
        # Just below risk boundary 0.7 (0.5*1.0 + 0.3*0.38 + 0.2*0.4 = 0.694)
        (100, 19, 0.4),
        # Just above risk boundary 0.7 (0.5*1.0 + 0.3*0.42 + 0.2*0.4 = 0.706)
        (100, 21, 0.4),
        # Exact motion spike threshold 0.7 (only +0.3 boost, second +0.6 NOT triggered because not > 0.7)
        (20, 10, 0.7),
        # Just above second motion spike threshold 0.7 (+0.3 and +0.6 boosts = +0.9)
        (20, 10, 0.7001),
        (10, 5, 0.8),
        # Full / max values (clamped to 1.0)
        (100, 50, 1.0),
        (100, 50, 0.0),
        (150, 80, 1.0),
    ]

    for crowd, devices, motion in test_cases:
        legacy_risk, legacy_alert = _legacy_calculate_risk(crowd, devices, motion)
        new_risk, new_alert = backend.calculate_risk(crowd, devices, motion)

        assert new_risk == legacy_risk, (
            f"Risk mismatch for ({crowd}, {devices}, {motion}): "
            f"new={new_risk} vs legacy={legacy_risk}"
        )
        assert new_alert == legacy_alert, (
            f"Alert mismatch for ({crowd}, {devices}, {motion}): "
            f"new={new_alert} vs legacy={legacy_alert}"
        )


def test_set_event_endpoint_and_active_profile_advice():
    client = backend.app.test_client()

    # Default profile check
    res_default = client.get("/data")
    assert res_default.status_code == 200
    p_def = res_default.get_json()
    assert p_def["profile"] == "default"
    assert p_def["profile_label"] == "Default (current model)"
    assert p_def["advice"] == "Normal monitoring."

    # Switch to valid profile
    set_res = client.post("/set_event", json={"profile": "procession_rally"})
    assert set_res.status_code == 200
    assert set_res.get_json()["status"] == "ok"
    assert set_res.get_json()["active_profile"] == "procession_rally"

    # Verify /data reflects new profile and its advice
    res_rally = client.get("/data")
    p_rally = res_rally.get_json()
    assert p_rally["profile"] == "procession_rally"
    assert p_rally["profile_label"] == "Procession or rally"
    assert p_rally["advice"] == "Keep routes clear."

    # Switch to invalid profile -> 400 error
    bad_res = client.post("/set_event", json={"profile": "nonexistent_profile"})
    assert bad_res.status_code == 400
    assert bad_res.get_json()["status"] == "error"

    # Profile remains procession_rally after failed attempt
    res_still_rally = client.get("/data")
    assert res_still_rally.get_json()["profile"] == "procession_rally"


def test_other_event_profiles_apply_custom_weights_and_thresholds():
    # Procession rally has heavy motion weight (0.45) and lower thresholds (yellow 35, red 65)
    rally_profile = backend.EVENT_PROFILES["procession_rally"]
    assert rally_profile["weights"]["M"] == 0.45
    assert rally_profile["yellow"] == 35
    assert rally_profile["red"] == 65

    # Seated audience has higher yellow 45 and red 75
    seated_profile = backend.EVENT_PROFILES["seated_audience"]
    assert seated_profile["weights"]["V"] == 0.50
    assert seated_profile["yellow"] == 45
    assert seated_profile["red"] == 75

    # Standing gathering
    standing_profile = backend.EVENT_PROFILES["standing_gathering"]
    assert standing_profile["weights"]["V"] == 0.45

    # Queue entry
    queue_profile = backend.EVENT_PROFILES["queue_entry"]
    assert queue_profile["weights"]["V"] == 0.40

    # Test procession_rally with motion > 0.4 triggers spike rule from JSON
    # crowd=0, devices=0, motion=0.5 -> base: 0.45*0.5 = 0.225. Spike boost: +0.3 -> 0.525.
    # 52.5 > yellow (35), so level should be Yellow -> MEDIUM
    r_val, alert, adv = backend.calculate_risk_and_advice(0, 0, 0.5, profile=rally_profile)
    assert r_val == 0.53
    assert alert == "MEDIUM"
    assert adv == rally_profile["advice"]["Yellow"]


