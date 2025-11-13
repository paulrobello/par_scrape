import pytest

from par_scrape import utils


@pytest.mark.parametrize("items,chunk_size,expected", [
    ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
    ([1, 2, 3], 1, [[1], [2], [3]]),
    ([], 3, []),
])
def test_chunk_list(items, chunk_size, expected):
    assert utils.chunk_list(items, chunk_size) == expected


def test_chunk_list_invalid_size():
    with pytest.raises(ValueError):
        utils.chunk_list([1, 2, 3], 0)


@pytest.mark.parametrize("a,b,expected", [
    (4, 2, 2.0),
    (1, 0, 0.0),
])
def test_safe_divide(a, b, expected):
    assert utils.safe_divide(a, b) == expected


def test_merge_dicts():
    a = {"a": 1, "b": 2}
    b = {"b": 3, "c": 4}
    result = utils.merge_dicts(a, b)
    assert result == {"a": 1, "b": 3, "c": 4}
