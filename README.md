from src import generate_truss, solve_truss_opensees


def test_solve_runs():
    sheets = generate_truss("Pratt", L=10.0, H=2.0, n_panels=6, chord_area=0.01, web_area=0.008, E=210000.0)
    res = solve_truss_opensees(sheets, load_case_id=1)
    assert "results_nodal" in res and "results_elements" in res
    assert not res["results_nodal"].empty
