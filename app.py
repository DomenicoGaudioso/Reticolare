import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src import (
    generate_truss, solve_truss_opensees, write_xlsx, ensure_sheets
)

st.set_page_config(page_title="Reticolare 2D — OpenSeesPy", layout="wide")

st.title("Reticolare 2D — Generatore parametrico + OpenSeesPy")
st.caption("Genera travi reticolari → risolvi → esporta")


def load_example(truss_type: str = "Warren"):
    return generate_truss(
        truss_type=truss_type,
        L=12.0,
        H=2.0,
        n_panels=8,
        chord_area=0.01,
        web_area=0.008,
        E=210000.0,
    )


if "sheets" not in st.session_state:
    st.session_state.sheets = None
if "results" not in st.session_state:
    st.session_state.results = None
if "initialized" not in st.session_state:
    st.session_state.initialized = True


with st.sidebar:
    st.header("Generatore Reticolare")
    
    st.subheader("Geometry")
    truss_type = st.selectbox("Tipo trave", [
        "Warren", "Howe", "Pratt", "Mohniè (K)", 
        "Nielsen", "Parabolica", "Parabolica rovescia", "Diagonale doppia"
    ])
    L = st.number_input("Lunghezza L (m)", value=12.0, min_value=1.0)
    H = st.number_input("Altezza H (m)", value=2.0, min_value=0.1)
    n_panels = st.number_input("Numero pannelli", value=8, min_value=2, max_value=50)
    
    st.subheader("Proprietà")
    chord_area = st.number_input("Area correnti (m²)", value=0.01, min_value=0.001)
    web_area = st.number_input("Area diagonali (m²)", value=0.008, min_value=0.001)
    E = st.number_input("E (MPa)", value=210000.0)
    
    if st.button("Genera Reticolare"):
        try:
            sheets = generate_truss(truss_type, L, H, n_panels, chord_area, web_area, E)
            st.session_state.sheets = ensure_sheets(sheets)
            st.session_state.results = None
            st.success(f"Generato: {len(sheets['nodes'])} nodi, {len(sheets['elements'])} elementi")
        except Exception as e:
            st.error(f"Errore: {e}")

    st.divider()
    
    if st.session_state.sheets is not None:
        lc_df = st.session_state.sheets.get("load_cases", pd.DataFrame())
        if lc_df is not None and not lc_df.empty and "id" in lc_df.columns:
            lc_ids = [int(x) for x in lc_df["id"].dropna().tolist()] or [1]
        else:
            lc_ids = [1]
    else:
        lc_ids = [1]
    active_lc = st.selectbox("Load case attivo", lc_ids, index=0)

    st.divider()
    st.header("Solve")
    
    if st.button("Valida modello"):
        if st.session_state.sheets is None:
            st.warning("Genera un reticolare prima.")
        elif st.session_state.sheets.get("nodes", pd.DataFrame()).empty:
            st.warning("Nodi vuoti.")
        else:
            st.success("Modello valido.")

    if st.button("Solve ▸ Linear Static"):
        if st.session_state.sheets is None:
            st.warning("Genera un reticolare prima.")
        else:
            try:
                st.session_state.results = solve_truss_opensees(
                    st.session_state.sheets,
                    int(active_lc)
                )
                st.success("Analisi completata.")
            except Exception as ex:
                st.exception(ex)

    st.divider()
    st.header("Export")
    if st.session_state.sheets is not None:
        out_sheets = st.session_state.sheets
        if st.session_state.results is not None:
            from src import results_to_sheets
            out_sheets = results_to_sheets(out_sheets, st.session_state.results)
        xbytes = write_xlsx(out_sheets)
        st.download_button("Scarica XLSX", data=xbytes, file_name="reticolare_output.xlsx")
    else:
        st.warning("Genera un reticolare prima.")


labels = ["nodes", "elements", "materials", "load_cases", "restraints", "node_loads", "results", "plot"]
tabs = st.tabs(labels)


def edit_sheet(name: str, default_cols: list):
    if st.session_state.sheets is None:
        st.warning("Genera un reticolare prima.")
        return
    df = st.session_state.sheets.get(name, pd.DataFrame(columns=default_cols))
    if df is None:
        df = pd.DataFrame(columns=default_cols)
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"edit_{name}")
    st.session_state.sheets[name] = edited


with tabs[0]:
    st.subheader("nodes (id, x, y)")
    edit_sheet("nodes", ["id", "x", "y"])

with tabs[1]:
    st.subheader("elements (id, n1, n2, A, matTag)")
    edit_sheet("elements", ["id", "n1", "n2", "A", "matTag"])

with tabs[2]:
    st.subheader("materials (matTag, type, E)")
    edit_sheet("materials", ["matTag", "type", "E"])

with tabs[3]:
    st.subheader("load_cases (id, name)")
    edit_sheet("load_cases", ["id", "name"])

with tabs[4]:
    st.subheader("restraints (load_case_id, node_id, ux, uy)")
    edit_sheet("restraints", ["load_case_id", "node_id", "ux", "uy"])

with tabs[5]:
    st.subheader("node_loads (load_case_id, node_id, fx, fy)")
    edit_sheet("node_loads", ["load_case_id", "node_id", "fx", "fy"])

with tabs[6]:
    st.subheader("results")
    if st.session_state.results is None:
        st.info("Esegui Solve per vedere i risultati.")
    else:
        st.markdown("### Nodi")
        st.dataframe(st.session_state.results["results_nodal"], use_container_width=True)
        st.markdown("### Elementi")
        st.dataframe(st.session_state.results["results_elements"], use_container_width=True)

with tabs[7]:
    st.subheader("plot")
    if st.session_state.sheets is None:
        st.warning("Genera un reticolare prima.")
    else:
        nodes = st.session_state.sheets.get("nodes", pd.DataFrame())
        elems = st.session_state.sheets.get("elements", pd.DataFrame())
        
        if nodes is None or nodes.empty:
            st.info("Nessun nodo.")
        else:
            coords = {int(r["id"]): (float(r["x"]), float(r["y"])) for _, r in nodes.iterrows()}
            fig = go.Figure()
            
            # Vincoli
            restraints = st.session_state.sheets.get("restraints", pd.DataFrame())
            if restraints is not None and not restraints.empty:
                for _, r in restraints.iterrows():
                    nid = int(r["node_id"])
                    if nid in coords:
                        x, y = coords[nid]
                        ux = int(r.get("ux", 0))
                        uy = int(r.get("uy", 0))
                        if ux and uy:
                            fig.add_trace(go.Scatter(x=[x], y=[y-0.15], mode="markers",
                                marker=dict(symbol="triangle-up", size=14, color="red"),
                                name="Incastro"))
                        elif uy:
                            fig.add_trace(go.Scatter(x=[x], y=[y-0.15], mode="markers",
                                marker=dict(symbol="circle", size=10, color="blue"),
                                name="Appoggio"))
            
            # Carichi
            node_loads = st.session_state.sheets.get("node_loads", pd.DataFrame())
            if node_loads is not None and not node_loads.empty:
                for _, nl in node_loads.iterrows():
                    nid = int(nl["node_id"])
                    if nid in coords:
                        fy = float(nl.get("fy", 0))
                        if fy != 0:
                            x, y = coords[nid]
                            fig.add_trace(go.Scatter(x=[x], y=[y+0.2], mode="markers+text",
                                marker=dict(symbol="arrow-down", size=12, color="orange"),
                                text=f"{abs(fy)}", textposition="top center", name="Carico"))
            
            # Elementi
            if elems is not None and not elems.empty:
                for _, e in elems.iterrows():
                    n1 = int(e["n1"])
                    n2 = int(e["n2"])
                    if n1 in coords and n2 in coords:
                        x1, y1 = coords[n1]
                        x2, y2 = coords[n2]
                        group = e.get("group", "")
                        color = "#888"
                        if group == "chord_bottom":
                            color = "#1f77b4"
                        elif group == "chord_top":
                            color = "#ff7f0e"
                        elif group == "diag":
                            color = "#2ca02c"
                        elif group == "vert":
                            color = "#9467bd"
                        fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="lines",
                            line=dict(color=color, width=3), showlegend=False))
            
            # Nodi
            fig.add_trace(go.Scatter(
                x=[coords[n][0] for n in coords],
                y=[coords[n][1] for n in coords],
                mode="markers", marker=dict(size=8, color="black"), showlegend=False
            ))
            
            # Deformata
            if st.session_state.results is not None:
                scale = st.slider("Scala deformata", 0.0, 1000.0, 100.0, 1.0)
                disp = st.session_state.results["results_nodal"].set_index("node_id")
                for _, e in elems.iterrows():
                    n1 = int(e["n1"])
                    n2 = int(e["n2"])
                    if n1 in disp.index and n2 in disp.index:
                        x1 = coords[n1][0] + scale * disp.loc[n1, "ux"]
                        y1 = coords[n1][1] + scale * disp.loc[n1, "uy"]
                        x2 = coords[n2][0] + scale * disp.loc[n2, "ux"]
                        y2 = coords[n2][1] + scale * disp.loc[n2, "uy"]
                        fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="lines",
                            line=dict(color="red", width=2, dash="solid"), showlegend=False))
            
            fig.update_layout(xaxis_title="X (m)", yaxis_title="Y (m)", height=500)
            st.plotly_chart(fig, use_container_width=True)