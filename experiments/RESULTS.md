# ZeroLeak Gate Test Results
Generated: 2026-09-17 23:09:04

| Test | Result | Detail |
|------|--------|--------|
| A: Digital baseline | ✅ PASS | status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0 |
| B: JPEG q75 compress | ✅ PASS | status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0 |
| C: JPEG q55 compress | ✅ PASS | status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0 |
| D: Cropped 70% | ❌ FAIL | status=CORRUPTED c=? h=? p=? bits=141 conf=0.5035714285714286 |
| E: Brightness +20 | ✅ PASS | status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0 |
| F: Rotation 3deg | ✅ PASS | status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0 |
| G: False-positive guard | ✅ PASS | status=UNKNOWN c=? h=? p=? bits=0 conf=0.0 |

**Gate Decision: 🟢 GO** (6/7 passed)

## Notes
- Tests A–F use digitally rendered images (no physical printer required)
- Physical print validation must be done manually with encode.py + decode.py
- Payload: centre=42, hall=7, print=13
