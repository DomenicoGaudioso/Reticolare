# src.py
from __future__ import annotations

from io import BytesIO
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import openseespy.opensees as ops

# =========================================================
# XLSX I/O
# =========================================================
REQUIRED_SHEETS = [
    "nodes",
    "elements",
    "materials",
    "load_cases",
    "restraints",
    "node_loads",
]


def read_xlsx(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    bio = BytesIO(file_bytes)
    xls = pd.ExcelFile(bio, engine="openpyxl")
    data: Dict[str, pd.DataFrame] = {}
    for sh in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sh, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        data[sh.strip().lower()] = df
    return data


def write_xlsx(sheets: Dict[str, pd.DataFrame]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=name[:31])
    return bio.getvalue()


def ensure_sheets(sheets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(sheets)
    for sh in REQUIRED_SHEETS:
        if sh not in out or out[sh] is None:
            out[sh] = pd.DataFrame()
    return out


# =========================================================
# Parametric truss generator
# =========================================================

TRUSS_TYPES = [
    "Warren",
    "Howe",
    "Pratt",
    "Mohniè (K)",
    "Nielsen",
    "Parabolica",
    "Parabolica rovescia",
    "Diagonale doppia",
]


def _parabola_y(x: float, L: float, h: float) -> float:
    # y(x) = 4h * x(L-x)/L^2, max = h at mid-span
    if L == 0:
        return 0.0
    return 4.0 * h * x * (L - x) / (L * L)


def generate_truss(
    truss_type: str,
    L: float,
    H: float,
    n_panels: int,
    chord_area: float,
    web_area: float,
    E: float,
    load_case_id: int = 1,
) -> Dict[str, pd.DataFrame]:
    """Generate a 2D simply supported parametric truss.

    Output is a dict of DataFrames compatible with the Streamlit app.

    Geometry:
      - Bottom chord nodes at y=0
      - Top chord nodes at y=H (flat) or parabolic for Parabolica / Parabolica rovescia
      - Panel points: n_panels panels, so n_panels+1 nodes per chord

    Supports:
      - Left bottom node: pin (ux=1, uy=1)
      - Right bottom node: roller (ux=0, uy=1)

    Notes on patterns:
      - This is a practical parametric implementation meant for rapid generation.
      - "Mohniè" is implemented as a K-truss (vertical + two diagonals per panel).
      - Nielsen is implemented as a "subdivided Pratt" (diagonals fanning toward mid-span).
    """
    truss_type = (truss_type or "Warren").strip()
    if truss_type not in TRUSS_TYPES:
        truss_type = "Warren"

    n_panels = int(max(1, n_panels))
    # Warren needs at least 4 panels to avoid singularity with end verticals
    if truss_type == "Warren" and n_panels < 4:
        n_panels = 4
    L = float(L)
    H = float(H)

    # x coordinates (uniform interasse)
    xs = np.linspace(0.0, L, n_panels + 1)

    # Node ids
    # bottom: 1..(n+1)
    # top: (n+2)..(2n+2)
    bottom_ids = list(range(1, n_panels + 2))
    top_ids = list(range(n_panels + 2, 2 * n_panels + 3))

    # Top y coordinates
    if truss_type == "Parabolica":
        top_ys = [_parabola_y(x, L, H) for x in xs]
    elif truss_type == "Parabolica rovescia":
        top_ys = [H - _parabola_y(x, L, H) for x in xs]
    else:
        top_ys = [H for _ in xs]

    nodes = []
    for i, nid in enumerate(bottom_ids):
        nodes.append({"id": nid, "x": float(xs[i]), "y": 0.0, "chord": "bottom"})
    for i, nid in enumerate(top_ids):
        nodes.append({"id": nid, "x": float(xs[i]), "y": float(top_ys[i]), "chord": "top"})

    nodes_df = pd.DataFrame(nodes)

    # Materials: single elastic material
    materials_df = pd.DataFrame([
        {"matTag": 1, "type": "Elastic", "E": float(E)}
    ])

    # Load cases
    load_cases_df = pd.DataFrame([
        {"id": int(load_case_id), "name": "LC1"}
    ])

    # Elements
    elems = []
    eid = 1

    def add_ele(n1, n2, A, group):
        nonlocal eid
        elems.append({
            "id": eid,
            "n1": int(n1),
            "n2": int(n2),
            "A": float(A),
            "matTag": 1,
            "group": group,
        })
        eid += 1

    # chords - Warren: bottom chord connects points where diagonals meet (not every panel)
    if truss_type == "Warren":
        for i in range(0, n_panels, 2):
            if i + 2 <= n_panels:
                add_ele(bottom_ids[i], bottom_ids[i + 2], chord_area, "chord_bottom")
    else:
        for i in range(n_panels):
            add_ele(bottom_ids[i], bottom_ids[i + 1], chord_area, "chord_bottom")
    for i in range(n_panels):
        add_ele(top_ids[i], top_ids[i + 1], chord_area, "chord_top")

    # web patterns
    if truss_type == "Warren":
        add_ele(bottom_ids[0], top_ids[0], web_area, "vert")
        add_ele(bottom_ids[n_panels], top_ids[n_panels], web_area, "vert")
        for i in range(0, n_panels - 1, 2):
            add_ele(bottom_ids[i], top_ids[i + 1], web_area, "diag")
            if i + 2 <= n_panels:
                add_ele(top_ids[i + 1], bottom_ids[i + 2], web_area, "diag")

    elif truss_type == "Howe":
        # Verticals at each panel point (including ends) + diagonals sloping toward center
        for i in range(n_panels + 1):
            add_ele(bottom_ids[i], top_ids[i], web_area, "vert")
        mid = n_panels / 2.0
        for i in range(n_panels):
            if i < mid:
                add_ele(bottom_ids[i], top_ids[i + 1], web_area, "diag")
            else:
                add_ele(top_ids[i], bottom_ids[i + 1], web_area, "diag")

    elif truss_type == "Pratt":
        # Verticals + diagonals sloping away from center (including ends)
        for i in range(n_panels + 1):
            add_ele(bottom_ids[i], top_ids[i], web_area, "vert")
        mid = n_panels / 2.0
        for i in range(n_panels):
            if i < mid:
                add_ele(top_ids[i], bottom_ids[i + 1], web_area, "diag")
            else:
                add_ele(bottom_ids[i], top_ids[i + 1], web_area, "diag")

    elif truss_type == "Diagonale doppia":
        # Verticals + X bracing each panel (including ends)
        for i in range(n_panels + 1):
            add_ele(bottom_ids[i], top_ids[i], web_area, "vert")
        for i in range(n_panels):
            add_ele(bottom_ids[i], top_ids[i + 1], web_area, "diag")
            add_ele(top_ids[i], bottom_ids[i + 1], web_area, "diag")

    elif truss_type == "Mohniè (K)":
        # K-truss: verticals + two diagonals meeting at mid of vertical
        # we create mid-nodes on each internal panel point of top chord (or bottom) as additional nodes.
        # Add mid nodes on verticals between bottom and top at each internal panel point.
        extra_nodes = []
        mid_ids = {}
        next_node_id = max(top_ids) + 1
        for i in range(1, n_panels):
            xb = float(xs[i])
            yb = 0.0
            yt = float(top_ys[i])
            ym = 0.5*(yb+yt)
            mid_ids[i] = next_node_id
            extra_nodes.append({"id": next_node_id, "x": xb, "y": ym, "chord": "mid"})
            next_node_id += 1
        if extra_nodes:
            nodes_df = pd.concat([nodes_df, pd.DataFrame(extra_nodes)], ignore_index=True)

        # vertical split: bottom-mid and mid-top
        for i in range(1, n_panels):
            m = mid_ids[i]
            add_ele(bottom_ids[i], m, web_area, "vert")
            add_ele(m, top_ids[i], web_area, "vert")

        # diagonals: create K in each panel using mid node
        for i in range(n_panels):
            # left half: connect mid at i+1 to bottom i and top i+1
            if 0 < i+1 < n_panels:
                m = mid_ids[i+1]
                add_ele(bottom_ids[i], m, web_area, "diag")
                add_ele(top_ids[i+1], m, web_area, "diag")
            # also connect mid at i to bottom i+1 and top i
            if 0 < i < n_panels:
                m = mid_ids[i]
                add_ele(bottom_ids[i+1], m, web_area, "diag")
                add_ele(top_ids[i], m, web_area, "diag")

    elif truss_type == "Nielsen":
        # Subdivided Pratt: diagonals in tension zones, longer diagonals toward midspan.
        # Include end verticals
        for i in range(n_panels + 1):
            add_ele(bottom_ids[i], top_ids[i], web_area, "vert")
        half = n_panels // 2
        # left fan
        for i in range(0, max(0, half-1)):
            j = i + 2
            if j <= n_panels:
                add_ele(top_ids[i], bottom_ids[j], web_area, "diag")
        # right fan (mirror)
        for i in range(n_panels, min(n_panels, half+1), -1):
            j = i - 2
            if j >= 0:
                add_ele(top_ids[i], bottom_ids[j], web_area, "diag")

        # add short diagonals to stabilize near ends
        for i in range(n_panels):
            if i % 2 == 0:
                add_ele(top_ids[i], bottom_ids[i+1], web_area, "diag")

    elif truss_type in ("Parabolica", "Parabolica rovescia"):
        # Parabolic chord - include end verticals
        for i in range(n_panels + 1):
            add_ele(bottom_ids[i], top_ids[i], web_area, "vert")
        mid = n_panels / 2.0
        for i in range(n_panels):
            if i < mid:
                add_ele(top_ids[i], bottom_ids[i + 1], web_area, "diag")
            else:
                add_ele(bottom_ids[i], top_ids[i + 1], web_area, "diag")

    elements_df = pd.DataFrame(elems)

    # Restraints: simple support at bottom ends
    # Pin (incastro 2D) on left, Roller (appoggio) on right
    restraints_df = pd.DataFrame([
        {"load_case_id": int(load_case_id), "node_id": int(bottom_ids[0]), "ux": 1, "uy": 1},
        {"load_case_id": int(load_case_id), "node_id": int(bottom_ids[-1]), "ux": 0, "uy": 1},
    ])

    # Default node loads: empty; provide an example load row (comment-like) at mid top node
    mid_top = top_ids[len(top_ids)//2]
    node_loads_df = pd.DataFrame([
        {"load_case_id": int(load_case_id), "node_id": int(mid_top), "fx": 0.0, "fy": -10.0}
    ])

    return {
        "nodes": nodes_df.sort_values("id").reset_index(drop=True),
        "elements": elements_df,
        "materials": materials_df,
        "load_cases": load_cases_df,
        "restraints": restraints_df,
        "node_loads": node_loads_df,
    }


# =========================================================
# OpenSeesPy solver (2D truss)
# =========================================================

def solve_truss_opensees(sheets: Dict[str, pd.DataFrame], load_case_id: int = 1) -> Dict[str, pd.DataFrame]:
    """Solve linear static 2D truss using OpenSeesPy.

    Uses:
      - model('basic','-ndm',2,'-ndf',2)
      - uniaxialMaterial('Elastic', matTag, E)
      - element('Truss', eleTag, iNode, jNode, A, matTag)
      - pattern('Plain',...), timeSeries('Linear',...)
      - eleResponse(eleTag,'axialForce')

    (These commands and truss queries are documented in OpenSees/OpenSeesPy docs.)
    """
    s = ensure_sheets(sheets)

    nodes = s["nodes"].copy()
    elements = s["elements"].copy()
    materials = s["materials"].copy()
    restraints = s["restraints"].copy()
    loads = s["node_loads"].copy()

    if nodes.empty or elements.empty or materials.empty:
        raise ValueError("nodes/elements/materials non possono essere vuoti")

    nodes["id"] = nodes["id"].astype(int)
    elements["id"] = elements["id"].astype(int)
    elements["n1"] = elements["n1"].astype(int)
    elements["n2"] = elements["n2"].astype(int)
    elements["matTag"] = elements["matTag"].astype(int)
    materials["matTag"] = materials["matTag"].astype(int)

    ops.wipe()

    # Planar truss: ndm=2, ndf=2
    ops.model('basic', '-ndm', 2, '-ndf', 2)

    # nodes
    for _, r in nodes.iterrows():
        ops.node(int(r['id']), float(r['x']), float(r['y']))

    # fixities
    if not restraints.empty:
        rr = restraints[restraints["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in rr.iterrows():
            nid = int(r['node_id'])
            ux = int(r.get('ux', 0))
            uy = int(r.get('uy', 0))
            ops.fix(nid, ux, uy)

    # materials
    for _, r in materials.iterrows():
        if str(r.get('type','Elastic')).strip().lower() == 'elastic':
            ops.uniaxialMaterial('Elastic', int(r['matTag']), float(r['E']))

    # elements
    for _, e in elements.iterrows():
        ops.element('Truss', int(e['id']), int(e['n1']), int(e['n2']), float(e['A']), int(e['matTag']))

    # loads
    ops.timeSeries('Linear', 1)
    ops.pattern('Plain', 1, 1)
    if not loads.empty:
        ll = loads[loads["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in ll.iterrows():
            ops.load(int(r['node_id']), float(r.get('fx', 0.0)), float(r.get('fy', 0.0)))

    # analysis (standard linear static)
    ops.system('BandSPD')
    ops.numberer('RCM')
    ops.constraints('Plain')
    ops.integrator('LoadControl', 1.0)
    ops.algorithm('Linear')
    ops.analysis('Static')

    ok = ops.analyze(1)
    if ok != 0:
        raise RuntimeError(f"OpenSees analyze failed with code={ok}")

    # reactions
    ops.reactions()

    # nodal results
    nodal_rows = []
    for nid in nodes['id'].tolist():
        ux = float(ops.nodeDisp(int(nid), 1))
        uy = float(ops.nodeDisp(int(nid), 2))
        rx = float(ops.nodeReaction(int(nid), 1))
        ry = float(ops.nodeReaction(int(nid), 2))
        nodal_rows.append({"node_id": int(nid), "ux": ux, "uy": uy, "Rx": rx, "Ry": ry})

    # element axial forces
    elem_rows = []
    for _, e in elements.iterrows():
        etag = int(e['id'])
        af = ops.eleResponse(etag, 'axialForce')
        # returns list-like; take first value
        val = float(af[0]) if hasattr(af, '__len__') and len(af) else float(af)
        elem_rows.append({
            "id": etag,
            "n1": int(e['n1']),
            "n2": int(e['n2']),
            "group": str(e.get('group','')),
            "axialForce": val,
            "A": float(e['A'])
        })

    return {
        "results_nodal": pd.DataFrame(nodal_rows),
        "results_elements": pd.DataFrame(elem_rows),
    }


def results_to_sheets(base_sheets: Dict[str, pd.DataFrame], results: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(base_sheets)
    for k, df in results.items():
        out[k] = df
    return out
