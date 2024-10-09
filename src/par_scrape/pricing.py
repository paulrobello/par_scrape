"""Pricing functions for Par Scrape."""

from typing import Tuple
import tiktoken
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from par_scrape.pricing_lookup import pricing_lookup
from par_scrape.utils import console, estimate_tokens


def calculate_price(
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
            input_token_count = len(encoder.encode(input_text))

            # Encode the output text to get the number of output tokens
            output_token_count = len(encoder.encode(output_text))
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
        if model in pricing_lookup:
            pricing_in = pricing_lookup[model]["input"]
            pricing_out = pricing_lookup[model]["output"]
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


def display_price_summary(
    status: Status, model: str, markdown, formatted_data_text
) -> None:
    """Display the price summary."""
    status.update("[bold cyan]Calculating token usage and cost...")
    input_tokens, output_tokens, total_cost = calculate_price(
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
