"""List the commodity names the old Agmarknet bulk file uses for Maharashtra.

Needed because rice and tur are named differently in the 2021-2025 file and the 2025-10 onward file, so
`build_price_history.py` only found 8 months for them. Output: ml/data_prep/old_source_commodities.txt
(one name per line, with the Maharashtra row count), which is then used to fill COMMODITY_ALIASES.

Run from the repo root:  python -I ml/data_prep/scan_commodity_names.py
"""

import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_price_history import SOURCES, stream_lines  # noqa: E402

OUT = Path(__file__).resolve().parent / "old_source_commodities.txt"


def main() -> int:
    counts: collections.Counter = collections.Counter()
    header = None
    rows = 0
    for line, offset in stream_lines(SOURCES["old"]):
        if header is None:
            header = next(csv.reader([line]))
            state_i, commodity_i = header.index("state_name"), header.index("commodity_name")
            continue
        rows += 1
        if rows % 4_000_000 == 0:
            print(f"{rows / 1e6:.0f}M rows, {offset / 1e9:.2f} GB, {len(counts)} names", flush=True)
        if "Maharashtra" not in line:
            continue
        parts = next(csv.reader([line]))
        if len(parts) == len(header) and parts[state_i] == "Maharashtra":
            counts[parts[commodity_i]] += 1
    OUT.write_text("\n".join(f"{n}\t{name}" for name, n in counts.most_common()), encoding="utf-8")
    print(f"[SUCCESS] {len(counts)} Maharashtra commodity names -> {OUT}", flush=True)
    for name, n in counts.most_common():
        low = name.lower()
        if any(k in low for k in ("paddy", "rice", "tur", "arhar", "red gram", "moth", "matki")):
            print(f"  MATCH {n:>8}  {name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
