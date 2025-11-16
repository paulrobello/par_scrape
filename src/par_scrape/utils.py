"""Utility functions for par_scrape."""


def chunk_list(items: list, chunk_size: int) -> list[list]:
    """
    Split a list into evenly sized chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def safe_divide(a: float, b: float) -> float:
    """
    Divide two numbers safely, returning 0 if division by zero occurs.
    """
    try:
        return a / b
    except ZeroDivisionError:
        return 0.0


def merge_dicts(a: dict, b: dict) -> dict:
    """
    Merge two dictionaries, with b overwriting keys from a.
    """
    return {**a, **b}
