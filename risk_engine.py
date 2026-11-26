"""Event-aware risk score. Event profiles live in config/event_profiles.json."""
from __future__ import annotations
import json
from pathlib import Path

CONFIG = Path(__file__).parent / "config" / "event_profiles.json"

def load_profiles(path: Path = CONFIG) -> dict:
    profiles = json.loads(Path(path).read_text())
    for name, p in profiles.items():
        w = p["weights"]
        if abs(sum(w.values()) - 1.0) > 1e-6:
            raise ValueError(f"{name}: weights must sum to 1")
        if not 0 <= p["yellow"] < p["red"] <= 100:
            raise ValueError(f"{name}: need 0 <= yellow < red <= 100")
    return profiles

def visual_score(people_in_zone: int, zone_capacity: int) -> float:
    """V in [0,1]: how full the zone is compared with its capacity."""
    return 0.0 if zone_capacity <= 0 else min(1.0, people_in_zone / zone_capacity)

def risk(V: float, W: float, M: float, profile: dict) -> tuple[float, str]:
    """Return (score 0-100, level). V, W, M must each be in [0,1]."""
    for v in (V, W, M):
        if not (-1e-9 <= v <= 1.0 + 1e-9):
            raise ValueError("V, W, M must be between 0 and 1")
    V = max(0.0, min(1.0, V))
    W = max(0.0, min(1.0, W))
    M = max(0.0, min(1.0, M))

    w = profile["weights"]
    base = w["V"] * V + w["W"] * W + w["M"] * M

    spike_boost = 0.0
    for s in profile.get("motion_spikes", []):
        if isinstance(s, dict):
            th = s.get("threshold", 0.0)
            boost = s.get("boost", 0.0)
        else:
            th, boost = s[0], s[1]
        if M > th:
            spike_boost += boost

    R = min(base + spike_boost, 1.0) * 100.0
    level = "Red" if R > profile["red"] else ("Yellow" if R > profile["yellow"] else "Green")
    return R, level

def advice(profile: dict, level: str) -> str:
    return profile.get("advice", {}).get(level, "")
