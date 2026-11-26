"""Small demo: same readings, different event types."""
import risk_engine as r
P = r.load_profiles()
V, W, M = 0.4, 0.4, 1.0
print(f"Readings: V={V}, W={W}, M={M}\n")
for name, p in P.items():
    R, lvl = r.risk(V, W, M, p)
    print(f"{p['label']:<26} R={R:5.1f}  {lvl:<6}  -> {r.advice(p, lvl)}")
