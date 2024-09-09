# PAR Scrape

[![PyPI](https://img.shields.io/pypi/v/par-scrape)](https://pypi.org/project/par-scrape/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/par-scrape.svg)](https://pypi.org/project/par-scrape/)  
![Runs on Linux | MacOS | Windows](https://img.shields.io/badge/runs%20on-Linux%20%7C%20MacOS%20%7C%20Windows-blue)
![Arch x86-63 | ARM | AppleSilicon](https://img.shields.io/badge/arch-x86--64%20%7C%20ARM%20%7C%20AppleSilicon-blue)  
![PyPI - License](https://img.shields.io/pypi/l/par-scrape)

## About
PAR Scrape is a versatile web scraping tool with options for Selenium or Playwright, featuring AI-powered data extraction and formatting.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/probello3)

## Screenshots
![PAR Scrape Screenshot](https://raw.githubusercontent.com/paulrobello/par_scrape/main/Screenshot.png)

## Features

- Web scraping using Selenium or Playwright
- AI-powered data extraction and formatting
- Supports multiple output formats (JSON, Excel, CSV, Markdown)
- Customizable field extraction
- Token usage and cost estimation

## Known Issues
- Silent mode on windows still shows message about websocket. There is no simple way to get rid of this.
- Providers other than OpenAI have not been tested you millage may vary

## Installation

To install PAR Scrape, make sure you have Python 3.11 or higher and [uv](https://pypi.org/project/uv/) installed.

### Installation From Source

Then, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/paulrobello/par_scrape.git
   cd par_scrape
   ```

2. Install the package dependencies using uv:
   ```bash
   uv sync
   ```
### Installation From PyPI

To install PAR Scrape from PyPI, run any of the following commands:

```bash
uv tool install par-scrape
```

```bash
pipx install par-scrape
```

## Usage

To use PAR Scrape, you can run it from the command line with various options. Here's a basic example:
Ensure you have the AI provider api key in your environment.
The key names for supported providers are as follows:
- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Google: `GOOGLE_API_KEY`
- Groq: `GROQ_API_KEY`
- Ollama: `Not needed`

You can also store your key in the file `~/.par-scrape.env` as follows:
```
OPENAI_API_KEY=your_api_key
ANTHROPIC_API_KEY=your_api_key
GOOGLE_API_KEY=your_api_key
GROQ_API_KEY=your_api_key
```

### Running from source
```bash
uv run par_scrape --url "https://openai.com/api/pricing/" --fields "Model" --fields "Pricing Input" --fields "Pricing Output" --scraper selenium --model gpt-4o-mini --display-output md
```

### Running if installed from PyPI
```bash
par_scrape --url "https://openai.com/api/pricing/" --fields "Title" "Number of Points" "Creator" "Time Posted" "Number of Comments" --scraper selenium --model gpt-4o-mini --display-output md
```

### Options

- `--url`, `-u`: The URL to scrape (default: "https://openai.com/api/pricing/")
- `--fields`, `-f`: Fields to extract from the webpage (default: ["Model", "Pricing Input", "Pricing Output"])
- `--scraper`: Scraper to use: 'selenium' or 'playwright' (default: "selenium")
- `--headless`, `-h`: Run in headless mode (for Selenium) (default: False)
- `--sleep-time`, `-t`: Time to sleep (in seconds) before scrolling and closing browser (default: 5)
- `--pause`, `-p`: Wait for user input before closing browser
- `--ai-provider`, `-a`: AI provider to use for processing (default: "OpenAI")
- `--model`, `-m`: AI model to use for processing. If not specified, a default model will be used based on the provider.
- `--pricing`: Enable pricing summary display (default: False)
- `--display-output`, `-d`: Display output in terminal (md, csv, or json)
- `--output-folder`, `-o`: Specify the location of the output folder (default: "./output")
- `--silent`, `-s`: Run in silent mode, suppressing output
- `--run-name`, `-n`: Specify a name for this run
- `--version`, `-v`: Show the version and exit
- `--cleanup`, `-c`: [none|before|after|both] If and when to remove the output folder (default: none)

### Examples

1. Basic usage with default options:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Model" -f "Pricing Input" -f "Pricing Output" --pricing
```
2. Using Playwright and displaying JSON output:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Title" -f "Description" -f "Price" --scraper playwright -d json --pricing
```
3. Specifying a custom model and output folder:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Title" -f "Description" -f "Price" --model gpt-4 --output-folder ./custom_output --pricing
```
4. Running in silent mode with a custom run name:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Title" -f "Description" -f "Price" --silent --run-name my_custom_run --pricing
```
5. Using the cleanup option to remove the output folder after scraping:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Title" -f "Description" -f "Price" --cleanup --pricing
```
6. Using the pause option to wait for user input before scrolling:
```bash
par_scrape --url "https://openai.com/api/pricing/" -f "Title" -f "Description" -f "Price" --pause --pricing
```

## Whats New
- Version 0.4.1:
  - Minor bug fixes for pricing summary.
  - Default model for google changed to "gemini-1.5-pro-exp-0827" which is free and usually works well.
- Version 0.4.0:
  - Added support for Anthropic, Google, Groq, and Ollama. (Not well tested with any providers other than OpenAI)
  - Add flag for displaying pricing summary. Defaults to False.
  - Added pricing data for Anthropic.
  - Better error handling for llm calls.
  - Updated cleanup flag to handle both before and after cleanup. Removed --remove-output-folder flag.
- Version 0.3.1:
  - Add pause and sleep-time options to control the browser and scraping delays.
  - Default headless mode to False so you can interact with the browser.
- Version 0.3.0:
  - Fixed location of config.json file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Paul Robello - probello@gmail.com
