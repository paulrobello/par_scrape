"""Pricing functions for Par Scrape."""

from typing import Tuple
import asyncio

import tiktoken
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from par_scrape.utils import console, estimate_tokens

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
    "claude-3-5-sonnet-20240620": {
        "input": 0.000003,  # $3.0 per 1M input tokens
        "output": 0.000015,  # $15.0 per 1M output tokens
    },
    "claude-3-haiku-20240307": {
        "input": 0.00000025,  # $0.25 per 1M input tokens
        "output": 0.00000125,  # $1.25 per 1M output tokens
    },
    "claude-3-sonnet-20240229": {
        "input": 0.000003,  # $3.0 per 1M input tokens
        "output": 0.000015,  # $15.0 per 1M output tokens
    },
    "claude-3-opus-20240229": {
        "input": 0.000015,  # $15.0 per 1M input tokens
        "output": 0.000075,  # $75.0 per 1M output tokens
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
    input_token_count = 0
    output_token_count = 0
    total_cost = 0.0
    try:
        try:
            # Initialize the encoder for the specific model
            encoder = tiktoken.encoding_for_model(model)

            # Encode the input text to get the number of input tokens
            input_token_count = await asyncio.to_thread(len, encoder.encode(input_text))

            # Encode the output text to get the number of output tokens
            output_token_count = await asyncio.to_thread(
                len, encoder.encode(output_text)
            )
        except Exception as _:  # pylint: disable=broad-except
            console.print(
                Panel.fit(
                    Text.assemble(
                        ("Could not get encoder. Falling back to estimator.", "yellow")
                    )
                )
            )
            input_token_count = estimate_tokens(input_text)
            output_token_count = estimate_tokens(output_text)

        # Calculate the costs
        if model in pricing:
            pricing_in = pricing[model]["input"]
            pricing_out = pricing[model]["output"]
        else:
            pricing_in = 0
            pricing_out = 0

        input_cost = input_token_count * pricing_in
        output_cost = output_token_count * pricing_out
        total_cost = input_cost + output_cost
    except Exception as _:  # pylint: disable=broad-except
        console.print(
            Panel.fit(
                Text.assemble(("Error calculating token usage and or cost.", "red"))
            )
        )
    return input_token_count, output_token_count, total_cost


async def display_price_summary(
    status: Status, model: str, markdown, formatted_data_text
) -> None:
    """Display the price summary."""
    status.update("[bold cyan]Calculating token usage and cost...")
    input_tokens, output_tokens, total_cost = await calculate_price(
        markdown, formatted_data_text, model=model
    )
    if input_tokens == 0 or output_tokens == 0:
        console.print(
            Panel.fit(
                Text.assemble(("Could not calculate token usage and cost.", "yellow"))
            )
        )
    else:
        console.print(
            Panel.fit(
                Text.assemble(
                    ("Input token count: ", "cyan"),
                    (f"{input_tokens}", "green"),
                    "\n",
                    ("Output token count: ", "cyan"),
                    (f"{output_tokens}", "green"),
                    "\n",
                    ("Estimated total cost: ", "cyan"),
                    (f"${total_cost:.4f}", "green bold"),
                ),
                title="[bold]Summary",
                border_style="bold",
            )
        )
