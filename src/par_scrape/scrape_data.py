"""Scrape data from Web."""

import json
import os
from pathlib import Path
from typing import List, Type, Tuple, Dict

import aiofiles
import pandas as pd
import tiktoken
from aiofiles import os as aos
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, create_model, ConfigDict
from rich.panel import Panel

from par_scrape.utils import console


async def save_raw_data(raw_data: str, run_name: str, output_folder: Path) -> str:
    """
    Save raw data to a file.

    Args:
        raw_data (str): The raw data to save.
        run_name (str): The run name to use in the filename.
        output_folder (str, optional): The folder to save the file in. Defaults to 'output'.

    Returns:
        str: The path to the saved file.
    """
    # Ensure the output folder exists
    await aos.makedirs(output_folder, exist_ok=True)

    # Save the raw markdown data with run_name in filename
    raw_output_path = os.path.join(output_folder, f"rawData_{run_name}.md")
    async with aiofiles.open(raw_output_path, "wt", encoding="utf-8") as f:
        await f.write(raw_data)
    console.print(
        Panel(f"Raw data saved to [bold green]{raw_output_path}[/bold green]")
    )
    return raw_output_path


def create_dynamic_listing_model(field_names: List[str]) -> Type[BaseModel]:
    """
    Dynamically creates a Pydantic model based on provided fields.

    Args:
        field_names (List[str]): A list of names of the fields to extract from the markdown.

    Returns:
        Type[BaseModel]: A dynamically created Pydantic model.
    """
    # Create field definitions using aliases for Field parameters
    field_definitions = {field: (str, ...) for field in field_names}
    # Dynamically create the model with all fields
    dynamic_listing_model = create_model(
        "DynamicListingModel",
        **field_definitions,  # type: ignore
    )  # type: ignore
    dynamic_listing_model.model_config = ConfigDict(arbitrary_types_allowed=True)
    return dynamic_listing_model


def create_listings_container_model(listing_model: Type[BaseModel]) -> Type[BaseModel]:
    """
    Create a container model that holds a list of the given listing model.

    Args:
        listing_model (Type[BaseModel]): The Pydantic model for individual listings.

    Returns:
        Type[BaseModel]: A container model for a list of listings.
    """
    return create_model("DynamicListingsContainer", listings=(List[listing_model], ...))


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
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        trimmed_text = encoder.decode(tokens[:max_tokens])
        return trimmed_text
    return text


async def format_data(
    data: str, dynamic_listings_container: Type[BaseModel], model: str
) -> BaseModel:
    """
    Format data using OpenAI's API asynchronously.

    Args:
        data (str): The input data to format.
        dynamic_listings_container (Type[BaseModel]): The Pydantic model to use for parsing.
        model (str): The OpenAI model to use for processing.

    Returns:
        BaseModel: The formatted data as a Pydantic model instance.
    """
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_message = """
You are an intelligent text extraction and conversion assistant. Your task is to extract structured information
from the given text and convert it into a pure JSON format. The JSON should contain only the structured data extracted from the text,
with no additional commentary, explanations, or extraneous information.
You could encounter cases where you can't find the data of the fields you have to extract or the data will be in a foreign language.
Please process the following text and provide the output in pure JSON format with no words before or after the JSON:"""

    user_message = f"Extract the following information from the provided text:\nPage content:\n\n{data}"

    try:
        completion = await client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            response_format=dynamic_listings_container,
        )
        return completion.choices[0].message.parsed  # type: ignore
    except (OpenAIError, json.JSONDecodeError) as e:
        console.print(
            f"[bold red]Error in API call or parsing response:[/bold red] {str(e)}"
        )
        return dynamic_listings_container(listings=[])


async def save_formatted_data(
    formatted_data: BaseModel, run_name: str, output_folder: Path
) -> Tuple[pd.DataFrame | None, Dict[str, str]]:
    """
    Save formatted data to JSON, Excel, CSV, and Markdown files.

    Args:
        formatted_data (BaseModel): The formatted data to save.
        run_name (str): The run name to use in the filenames.
        output_folder (str, optional): The folder to save the files in. Defaults to 'output'.

    Returns:
        Tuple[pd.DataFrame | None, Dict[str, str]]: The DataFrame created from the formatted data and a dictionary of
        file paths, or None and an empty dict if an error occurred.
    """
    file_paths: Dict[str, str] = {}
    # Ensure the output folder exists
    await aos.makedirs(output_folder, exist_ok=True)

    # Prepare formatted data as a dictionary
    formatted_data_dict = formatted_data.model_dump()

    # Save the formatted data as JSON with run_name in filename
    json_output_path = os.path.join(output_folder, f"sorted_data_{run_name}.json")
    with open(json_output_path, "wt", encoding="utf-8") as f:
        json.dump(formatted_data_dict, f, indent=4)
    console.print(
        Panel(
            f"Formatted data saved to JSON at [bold green]{json_output_path}[/bold green]"
        )
    )
    file_paths["json"] = json_output_path

    # Prepare data for DataFrame
    if isinstance(formatted_data_dict, dict):
        # If the data is a dictionary containing lists, assume these lists are records
        data_for_df = (
            next(iter(formatted_data_dict.values()))
            if len(formatted_data_dict) == 1
            else formatted_data_dict
        )
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError(
            "Formatted data is neither a dictionary nor a list, cannot convert to DataFrame"
        )

    # Create DataFrame
    try:
        df = pd.DataFrame(data_for_df)
        console.print(Panel("[bold green]DataFrame created successfully.[/bold green]"))

        # Save the DataFrame to an Excel file
        excel_output_path = os.path.join(output_folder, f"sorted_data_{run_name}.xlsx")
        df.to_excel(excel_output_path, index=False)
        console.print(
            Panel(
                f"Formatted data saved to Excel at [bold green]{excel_output_path}[/bold green]"
            )
        )
        file_paths["excel"] = excel_output_path

        # Save the DataFrame to a CSV file
        csv_output_path = os.path.join(output_folder, f"sorted_data_{run_name}.csv")
        df.to_csv(csv_output_path, index=False)
        console.print(
            Panel(
                f"Formatted data saved to CSV at [bold green]{csv_output_path}[/bold green]"
            )
        )
        file_paths["csv"] = csv_output_path

        # Save the DataFrame as a Markdown table
        markdown_output_path = os.path.join(output_folder, f"sorted_data_{run_name}.md")
        with open(markdown_output_path, "wt", encoding="utf-8") as f:
            f.write(df.to_markdown(index=False) or "")
        console.print(
            Panel(
                f"Formatted data saved as Markdown table at [bold green]{markdown_output_path}[/bold green]"
            )
        )
        file_paths["md"] = markdown_output_path

        return df, file_paths
    except Exception as e:  # pylint: disable=broad-except
        console.print(
            f"[bold red]Error creating DataFrame or saving files:[/bold red] {str(e)}"
        )
        return None, {}
