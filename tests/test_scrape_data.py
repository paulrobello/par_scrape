import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import BaseModel

from par_scrape.enums import OutputFormat
from par_scrape.scrape_data import (
    create_container_model,
    create_dynamic_model,
    format_data,
    save_formatted_data,
    save_raw_data,
)

# ---------- save_raw_data ----------


@pytest.mark.parametrize("as_dir", [True, False])
def test_save_raw_data_creates_file_and_logs(tmp_path, mocker, as_dir):
    mock_print = mocker.patch("par_scrape.scrape_data.console_out.print")

    if as_dir:
        output_base = tmp_path / "run1"
        output_base.mkdir()
        expected_path = output_base / "raw_data.md"
    else:
        output_base = tmp_path / "base"
        expected_path = Path(str(output_base) + "-raw.md")

    result_path = save_raw_data("hello world", output_base)

    assert result_path == expected_path
    assert result_path.read_text(encoding='utf-8') == "hello world"
    mock_print.assert_called_once()


# ---------- dynamic model helpers ----------


def test_create_dynamic_model_and_container_basic():
    fields = ["title", "price"]
    DynamicModel = create_dynamic_model(fields)
    ContainerModel = create_container_model(DynamicModel)

    item = DynamicModel(title="Test", price="$10")
    container = ContainerModel(listings=[item])

    assert isinstance(item, BaseModel)
    assert isinstance(container, BaseModel)
    assert container.listings[0].title == "Test"
    assert container.listings[0].price == "$10"


# ---------- format_data ----------


def test_format_data_success(tmp_path, mocker):
    # Prepare prompt file
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")

    # Dynamic models
    DynamicModel = create_dynamic_model(["title"])
    ContainerModel = create_container_model(DynamicModel)
    empty_container = ContainerModel(listings=[])

    # Mocks for LLM pipeline
    mock_chat_model = mocker.Mock()
    mock_structure_model = mocker.Mock()
    mock_chat_model.with_structured_output.return_value = mock_structure_model

    mock_llm_config = mocker.Mock()
    mock_llm_config.build_chat_model.return_value = mock_chat_model

    mocker.patch(
        "par_scrape.scrape_data.llm_run_manager.get_runnable_config",
        return_value={},
    )

    mock_structure_model.invoke.return_value = empty_container

    result = format_data(
        data="some text",
        dynamic_listings_container=ContainerModel,
        llm_config=mock_llm_config,
        prompt_cache=False,
        extraction_prompt=prompt_path,
    )

    mock_llm_config.build_chat_model.assert_called_once()
    mock_chat_model.with_structured_output.assert_called_once_with(ContainerModel)
    mock_structure_model.invoke.assert_called_once()
    assert result is empty_container


def test_format_data_failure_returns_empty_container(tmp_path, mocker):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("system prompt", encoding="utf-8")

    DynamicModel = create_dynamic_model(["title"])
    ContainerModel = create_container_model(DynamicModel)

    # Force an exception during API call
    mock_chat_model = mocker.Mock()
    mock_chat_model.with_structured_output.side_effect = RuntimeError("boom")

    mock_llm_config = mocker.Mock()
    mock_llm_config.build_chat_model.return_value = mock_chat_model

    mock_print = mocker.patch("par_scrape.scrape_data.console_out.print")

    result = format_data(
        data="some text",
        dynamic_listings_container=ContainerModel,
        llm_config=mock_llm_config,
        prompt_cache=False,
        extraction_prompt=prompt_path,
    )

    # On error, it should return an empty container
    assert isinstance(result, BaseModel)
    assert hasattr(result, "listings")
    assert result.listings == []
    mock_print.assert_called()  # error was logged


# ---------- save_formatted_data ----------


class Listing(BaseModel):
    title: str
    price: str


class ListingContainer(BaseModel):
    listings: list[Listing]


@pytest.mark.parametrize(
    "formats",
    [
        [OutputFormat.JSON],
        [OutputFormat.JSON, OutputFormat.CSV, OutputFormat.MARKDOWN],
    ],
)
def test_save_formatted_data_creates_files(tmp_path, mocker, formats):
    mock_print = mocker.patch("par_scrape.scrape_data.console_out.print")

    data = ListingContainer(
        listings=[Listing(title="Item 1", price="$10"), Listing(title="Item 2", price="$20")]
    )

    df, paths = save_formatted_data(
        formatted_data=data,
        output_formats=formats,
        run_name="run1",
        output_folder=tmp_path,
    )

    # DataFrame should not be empty
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    # JSON should always be created when requested
    if OutputFormat.JSON in formats:
        json_path = tmp_path / "extracted_data.json"
        assert json_path.exists()
        # quick sanity check that the file is valid JSON
        json.loads(json_path.read_text(encoding="utf-8"))
        assert paths[OutputFormat.JSON] == json_path

    # CSV
    if OutputFormat.CSV in formats:
        csv_path = tmp_path / "extracted_data.csv"
        assert csv_path.exists()
        assert paths[OutputFormat.CSV] == csv_path

    # Markdown
    if OutputFormat.MARKDOWN in formats:
        md_path = tmp_path / "extracted_data.md"
        assert md_path.exists()
        assert paths[OutputFormat.MARKDOWN] == md_path

    mock_print.assert_called()


class WeirdModel(BaseModel):
    """Model that returns unsupported type from model_dump."""

    value: int

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        return "not-a-dict-or-list"


def test_save_formatted_data_invalid_model(tmp_path):
    weird = WeirdModel(value=42)

    with pytest.raises(ValueError, match="neither a dictionary nor a list"):
        save_formatted_data(
            formatted_data=weird,
            output_formats=[OutputFormat.JSON],
            run_name="run1",
            output_folder=tmp_path,
        )
