"""Representative 3D structures for extracted compounds, via PubChem.

These are PubChem's computed conformers for the *compound*, NOT the
geometry the paper's calculation used — that only exists in the paper/SI
coordinate tables. Every file this module writes carries that provenance
in its comment line, and callers must keep geometry_source honest.
"""
import time

import requests

from . import config

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def pubchem_xyz(name):
    """Resolve a compound name to (xyz_text, cid); returns (None, msg) on
    failure. Tries the 3D conformer first, falls back to 2D coordinates
    (still useful for connectivity/sanity checks; flagged in the comment)."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    for record_type, tag in (("3d", "3D conformer"), ("2d", "2D coordinates")):
        resp = session.get(
            f"{PUG}/compound/name/{requests.utils.quote(name)}/SDF",
            params={"record_type": record_type}, timeout=60)
        time.sleep(config.REQUEST_INTERVAL)
        if resp.status_code != 200:
            continue
        parsed = _sdf_to_xyz(resp.text, name, tag)
        if parsed:
            return parsed
    return None, f"PubChem has no resolvable record for {name!r}"


def _sdf_to_xyz(sdf, name, tag):
    lines = sdf.splitlines()
    if len(lines) < 5:
        return None
    counts = lines[3].split()
    try:
        natoms = int(counts[0])
    except (ValueError, IndexError):
        return None
    cid = ""
    for i, l in enumerate(lines):
        if "PUBCHEM_COMPOUND_CID" in l and i + 1 < len(lines):
            cid = lines[i + 1].strip()
            break
    atoms = []
    for l in lines[4:4 + natoms]:
        parts = l.split()
        if len(parts) < 4:
            return None
        x, y, z, el = parts[0], parts[1], parts[2], parts[3]
        atoms.append(f"{el:2s}  {float(x):12.6f} {float(y):12.6f} {float(z):12.6f}")
    comment = (f"{name} | PubChem CID {cid} {tag} | GENERATED structure, "
               "NOT the geometry used in the referenced paper")
    return "\n".join([str(natoms), comment, *atoms]) + "\n", cid


def save_structure(entry_id, name):
    """Fetch and save database/structures/<entry_id>.xyz; returns
    (path_or_None, detail)."""
    result, detail = pubchem_xyz(name)
    if result is None:
        return None, detail
    xyz, cid = result, detail
    dest = config.DATABASE_DIR / "structures" / f"{entry_id}.xyz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(xyz)
    return dest, f"PubChem CID {cid}"
