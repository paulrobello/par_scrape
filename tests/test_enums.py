import pytest
from par_scrape.enums import CleanupType, OutputFormat


def test_cleanup_type_members_and_values():
    """Ensure CleanupType defines the expected options with correct string values."""
    expected = {
        "NONE": "none",
        "BEFORE": "before",
        "AFTER": "after",
        "BOTH": "both",
    }
    assert set(CleanupType.__members__.keys()) == set(expected.keys())
    for name, value in expected.items():
        assert CleanupType[name].value == value


@pytest.mark.parametrize("name,value", [
    ("MARKDOWN", "md"),
    ("JSON", "json"),
    ("CSV", "csv"),
    ("EXCEL", "excel"),
])
def test_output_format_members_and_values(name, value):
    """Ensure OutputFormat members match expected names and values."""
    member = OutputFormat[name]
    assert isinstance(member.value, str)
    assert member.value == value


def test_enum_uniqueness_and_iterability():
    """Verify both enums are iterable and have unique values."""
    cleanup_values = [m.value for m in CleanupType]
    output_values = [m.value for m in OutputFormat]
    assert len(cleanup_values) == len(set(cleanup_values))
    assert len(output_values) == len(set(output_values))
