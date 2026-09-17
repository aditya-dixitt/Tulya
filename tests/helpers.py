"""Tiny in-memory fixtures. No test touches data/out - the measured artefacts
are evidence, and a test suite that can overwrite its own evidence is not
evidence."""
import json
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "api") not in sys.path:
    sys.path.insert(0, str(ROOT / "api"))

from engine.attributes import extract
from engine.normalize import normalize


def frames(rows):
    """rows: list of (record_id, cpse, plant, legacy_code, description, uom, qty, unit_value)
    -> (recs, prep) indexed by record_id, prepared exactly as the pipeline does."""
    recs = pd.DataFrame(rows, columns=["record_id", "cpse", "plant", "legacy_code",
                                       "description", "uom", "qty", "unit_value"])
    norm = [normalize(d) for d in recs.description]
    attrs = [extract(n) for n in norm]
    prep = pd.DataFrame({
        "record_id": recs.record_id,
        "norm": norm,
        "attrs": [json.dumps(a) for a in attrs],
        "category": [__import__("engine.block", fromlist=["x"]).category_of(n) for n in norm],
        "bucket": ["NA"] * len(recs),
    })
    return recs.set_index("record_id"), prep.set_index("record_id")


def bolts():
    """Three M12x50 SS316 bolts under three codes, plus an M16 hard negative."""
    return frames([
        (1, "IOCL", "Panipat Refinery", "10001",
         "Hexagonal Bolt M12 x 50 mm Stainless Steel 316", "nos", 100, 50.0),
        (2, "IOCL", "Mathura Refinery", "10002",
         "HEX BOLT M12X50MM SS316", "nos", 200, 55.0),
        (3, "BPCL", "Kochi Refinery", "B-900",
         "hexagonal bolt M12 x 50 mm stainless steel 316", "nos", 50, 48.0),
        (4, "IOCL", "Panipat Refinery", "10003",
         "Hexagonal Bolt M16 x 50 mm Stainless Steel 316", "nos", 10, 70.0),
    ])


def truncated_cables():
    """The MAKTX failure: two cables whose voltage survived, two whose did not.

    Reproduces what the IOCL round trip found - a record with an unreadable
    hard key contradicts nothing and can therefore bridge two items that do
    contradict each other.
    """
    return frames([
        (10, "IOCL", "Mumbai Terminal", "M-1",
         "XLPE armoured cable 2 core 185 sqmm 6.6 kv", "m", 500, 900.0),
        (11, "IOCL", "Haldia Refinery", "M-2",
         "XLPE armoured cable 2 core 185 sqmm 33 kv", "m", 400, 1400.0),
        (12, "IOCL", "Paradip Refinery", "M-3",
         "XLPE armoured cable 2 core 185 sqmm", "m", 300, 1000.0),
    ])
