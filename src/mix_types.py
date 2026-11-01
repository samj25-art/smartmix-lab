"""Registry of concrete mix-design methods offered by the app.

Add a new method by writing an engine module (inputs dataclass + design function returning
rows / steps / checks / warnings) and registering it here; the UI lists whatever is registered.
Only methods with status 'available' are implemented - the rest are placeholders, not features.
"""
from __future__ import annotations

MIX_TYPES = [
    {"key": "normal", "label": "Normal-weight concrete (IS 10262:2019)", "status": "available",
     "engine": "src/engineering.py", "scope": "M10-M100, ordinary + high strength"},
    {"key": "leca", "label": "Lightweight aggregate concrete - LECA", "status": "available",
     "engine": "src/lwac.py", "scope": "Density-closure volume method, absorption-water split, "
                                        "sand-lightweight and all-lightweight mixes"},
    {"key": "scc", "label": "Self-compacting concrete (IS 10262 Sec. 4)", "status": "planned",
     "engine": "-", "scope": "not implemented"},
    {"key": "mass", "label": "Mass concrete (IS 10262 Sec. 5)", "status": "planned",
     "engine": "-", "scope": "not implemented"},
    {"key": "foam", "label": "Foamed / aerated concrete", "status": "planned",
     "engine": "-", "scope": "not implemented"},
]
