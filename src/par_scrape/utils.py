"""Utility functions for par_scrape."""

import tiktoken


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a given text.

    Args:
        text (str): The input text to estimate the number of tokens for.

    Returns:
        int: The estimated number of tokens.
    """
    try:
        return int(len(text) / 3) + 3
    except KeyError:
        return len(text)


def trim_to_token_limit(text: str, model: str, max_tokens: int = 200000) -> str:
    """
    Trim text to a specified token limit for a given model.

    Args:
        text (str): The input text to trim.
        model (str): The model name to use for tokenization.
        max_tokens (int, optional): The maximum number of tokens. Defaults to 200000.

    Returns:
        str: The trimmed text.
    """
    try:
        encoder = tiktoken.encoding_for_model(model)
        tokens = encoder.encode(text)
        if len(tokens) > max_tokens:
            return encoder.decode(tokens[:max_tokens])
    except KeyError:
        tokens = estimate_tokens(text)
        if tokens > max_tokens:
            return text[: max_tokens * 3]

    return text
