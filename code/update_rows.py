"""Update EXISTING aimdb rows in place from JSON files.
add-row refuses duplicate entry_ids, so rewriting an existing row must go
through the CSV directly. Only non-empty JSON fields overwrite; entry_id
must already exist.
"""
import csv, json, sys, os
CSV = "database/aimdb.csv"
rows = list(csv.DictReader(open(CSV)))
cols = list(rows[0].keys())
idx = {r["entry_id"]: r for r in rows}
changed = 0
for path in sys.argv[1:]:
    d = json.load(open(path))
    eid = d["entry_id"]
    if eid not in idx:
        print("SKIP (not present):", eid); continue
    tgt = idx[eid]
    for k, v in d.items():
        if k in cols and isinstance(v, str) and v.strip():
            tgt[k] = v
    changed += 1
    print("updated", eid, "Other=", len(tgt["Other"]))
w = csv.DictWriter(open(CSV, "w", newline=""), fieldnames=cols)
w.writeheader(); w.writerows(rows)
print("rows changed:", changed, "total:", len(rows))
