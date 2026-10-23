from books.services import acyclic_prerequisites


def test_cycles_are_dropped_keeping_book_order():
    order = {1: 0, 2: 1, 3: 2}
    kept = acyclic_prerequisites({(1, 2), (2, 3), (3, 1)}, order)
    assert set(kept) == {(1, 2), (2, 3)}


def test_self_loops_are_dropped():
    assert acyclic_prerequisites({(1, 1), (1, 2)}, {1: 0, 2: 1}) == [(1, 2)]
