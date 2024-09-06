"""Pricing functions for Par Scrape."""

from typing import Tuple
import asyncio

import tiktoken

pricing = {
    "gpt-4o": {
        "input": 0.000005,  # $5.00 per 1M input tokens
        "output": 0.000015,  # $15.00 per 1M output tokens
    },
    "gpt-4o-2024-08-06": {
        "input": 0.0000025,  # $2.50 per 1M input tokens
        "output": 0.00001,  # $10.00 per 1M output tokens
    },
    "gpt-4o-2024-05-13": {
        "input": 0.000005,  # $5.00 per 1M input tokens
        "output": 0.000015,  # $15.00 per 1M output tokens
    },
    "gpt-4o-mini": {
        "input": 0.00000015,  # $0.15 per 1M input tokens
        "output": 0.0000006,  # $0.60 per 1M output tokens
    },
    "gpt-4o-mini-2024-07-18": {
        "input": 0.00000015,  # $0.15 per 1M input tokens
        "output": 0.0000006,  # $0.60 per 1M output tokens
    },
    "gpt-4": {
        "input": 0.00003,  # $30.00 per 1M input tokens
        "output": 0.00006,  # $60.00 per 1M output tokens
    },
    "gpt-4-32k": {
        "input": 0.00006,  # $60.00 per 1M input tokens
        "output": 0.00012,  # $120.00 per 1M output tokens
    },
    "gpt-4-turbo": {
        "input": 0.00001,  # $10.00 per 1M input tokens
        "output": 0.00003,  # $30.00 per 1M output tokens
    },
    "gpt-4-turbo-2024-04-09": {
        "input": 0.00001,  # $10.00 per 1M input tokens
        "output": 0.00003,  # $30.00 per 1M output tokens
    },
    "gpt-3.5-turbo-0125": {
        "input": 0.0000005,  # $0.50 per 1M input tokens
        "output": 0.0000015,  # $1.50 per 1M output tokens
    },
}


async def calculate_price(
    input_text: str, output_text: str, model: str
) -> Tuple[int, int, float]:
    """
    Calculate the price for processing input and output text using a specified model.

    Args:
        input_text (str): The input text.
        output_text (str): The output text.
        model (str, optional): The model to use for pricing. Defaults to model_used.

    Returns:
        Tuple[int, int, float]: A tuple containing the input token count, output token count, and total cost.
        Returns (0, 0, 0.0) if there's an error during calculation.
    """
    try:
        # Initialize the encoder for the specific model
        encoder = tiktoken.encoding_for_model(model)

        # Encode the input text to get the number of input tokens
        input_token_count = await asyncio.to_thread(len, encoder.encode(input_text))

        # Encode the output text to get the number of output tokens
        output_token_count = await asyncio.to_thread(len, encoder.encode(output_text))

        # Calculate the costs
        # Convert price per million tokens to price per token, then multiply by token count
        input_cost = input_token_count * pricing[model]["input"]
        output_cost = output_token_count * pricing[model]["output"]
        total_cost = input_cost + output_cost

        return input_token_count, output_token_count, total_cost
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error calculating price: {str(e)}")
        return 0, 0, 0.0
