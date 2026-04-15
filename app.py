from src import generate_truss


def test_generate_warren():
    sheets = generate_truss("Warren", L=12.0, H=2.0, n_panels=8, chord_area=0.01, web_area=0.008, E=210000.0)
    assert not sheets["nodes"].empty
    assert not sheets["elements"].empty
    # 2 chords: 2*n_panels elements
    assert (sheets["elements"].shape[0] >= 2*8)
