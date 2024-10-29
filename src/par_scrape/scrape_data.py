"""Scrape data from Web."""

import json
import os
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, create_model, ConfigDict
from rich.panel import Panel

from par_scrape.utils import console
from par_scrape.lib.llm_config import LlmConfig
from par_scrape.lib.llm_providers import LlmProvider


def save_raw_data(raw_data: str, run_name: str, output_folder: Path) -> str:
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
    os.makedirs(output_folder, exist_ok=True)

    # Save the raw markdown data with run_name in filename
    raw_output_path = os.path.join(output_folder, f"rawData_{run_name}.md")
    with open(raw_output_path, "w", encoding="utf-8") as f:
        f.write(raw_data)
    console.print(Panel(f"Raw data saved to [bold green]{raw_output_path}[/bold green]"))
    return raw_output_path


def create_dynamic_listing_model(field_names: list[str]) -> type[BaseModel]:
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


def create_listings_container_model(listing_model: type[BaseModel]) -> type[BaseModel]:
    """
    Create a container model that holds a list of the given listing model.

    Args:
        listing_model (Type[BaseModel]): The Pydantic model for individual listings.

    Returns:
        Type[BaseModel]: A container model for a list of listings.
    """
    return create_model("DynamicListingsContainer", listings=(list[listing_model], ...))


# pylint: disable=too-many-positional-arguments
def format_data(
    data: str,
    dynamic_listings_container: type[BaseModel],
    model: str,
    ai_provider: LlmProvider,
    extraction_prompt: Path | None = None,
    ai_base_url: str | None = None,
) -> BaseModel:
    """
    Format data using the specified AI provider's API.

    Args:
        data (str): The input data to format.
        dynamic_listings_container (Type[BaseModel]): The Pydantic model to use for parsing.
        model (str): The AI model to use for processing.
        ai_provider (LlmProvider): The AI provider to use for processing.
        extraction_prompt (Path): Path to the extraction prompt file.
        ai_base_url (str): The base URL for the AI provider.

    Returns:
        BaseModel: The formatted data as a Pydantic model instance.
    """
    if not extraction_prompt:
        extraction_prompt = Path(__file__).parent / "extraction_prompt.md"
    try:
        system_message = extraction_prompt.read_text(encoding="utf-8")
    except FileNotFoundError:
        console.print(f"[bold red]Extraction prompt file not found: {extraction_prompt}[/bold red]")
        raise

    user_message = f"Extract the following information from the provided text:\nPage content:\n\n{data}"

    try:
        llm_config = LlmConfig(provider=ai_provider, model_name=model, temperature=0, base_url=ai_base_url)
        chat_model = llm_config.build_chat_model()

        structure_model = chat_model.with_structured_output(
            dynamic_listings_container  # , include_raw=True
        )
        data = structure_model.invoke(
            [
                ("system", system_message),
                ("user", user_message),
            ]
        )  # type: ignore
        if isinstance(data, BaseModel):
            return data
        console.print(data)
        raise ValueError("Error in API call. Did not return a Pydantic BaseModel")
    except Exception as e:  # pylint: disable=broad-exception-caught
        console.print(f"[bold red]Error in API call or parsing response:[/bold red] {str(e)}")
        return dynamic_listings_container(listings=[])


def save_formatted_data(
    formatted_data: BaseModel, run_name: str, output_folder: Path
) -> tuple[pd.DataFrame | None, dict[str, Path]]:
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
    file_paths: dict[str, Path] = {}
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Prepare formatted data as a dictionary
    formatted_data_dict = formatted_data.model_dump()

    # Save the formatted data as JSON with run_name in filename
    json_output_path = output_folder / f"sorted_data_{run_name}.json"
    json_output_path.write_text(json.dumps(formatted_data_dict, indent=4), encoding="utf-8")

    console.print(Panel(f"Formatted data saved to JSON at [bold green]{json_output_path}[/bold green]"))
    file_paths["json"] = json_output_path

    # Prepare data for DataFrame
    if isinstance(formatted_data_dict, dict):
        # If the data is a dictionary containing lists, assume these lists are records
        data_for_df = next(iter(formatted_data_dict.values())) if len(formatted_data_dict) == 1 else formatted_data_dict
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError("Formatted data is neither a dictionary nor a list, cannot convert to DataFrame")

    # Create DataFrame
    try:
        df = pd.DataFrame(data_for_df)
        console.print(Panel("[bold green]DataFrame created successfully.[/bold green]"))

        # Save the DataFrame to an Excel file
        excel_output_path = output_folder / f"sorted_data_{run_name}.xlsx"
        df.to_excel(excel_output_path, index=False)
        console.print(Panel(f"Formatted data saved to Excel at [bold green]{excel_output_path}[/bold green]"))
        file_paths["excel"] = excel_output_path

        # Save the DataFrame to a CSV file
        csv_output_path = output_folder / f"sorted_data_{run_name}.csv"
        df.to_csv(csv_output_path, index=False)
        console.print(Panel(f"Formatted data saved to CSV at [bold green]{csv_output_path}[/bold green]"))
        file_paths["csv"] = csv_output_path

        # Save the DataFrame as a Markdown table
        markdown_output_path = output_folder / f"sorted_data_{run_name}.md"
        markdown_output_path.write_text(df.to_markdown(index=False) or "", encoding="utf-8")
        console.print(
            Panel(f"Formatted data saved as Markdown table at [bold green]{markdown_output_path}[/bold green]")
        )
        file_paths["md"] = markdown_output_path

        return df, file_paths
    except Exception as e:  # pylint: disable=broad-except
        console.print(f"[bold red]Error creating DataFrame or saving files:[/bold red] {str(e)}")
        return None, {}
