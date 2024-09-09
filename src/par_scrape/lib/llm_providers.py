"""LLM provider types."""

from __future__ import annotations

from enum import Enum


class LlmProvider(str, Enum):
    """Llm provider types."""

    OLLAMA = "Ollama"
    OPENAI = "OpenAI"
    GROQ = "Groq"
    ANTHROPIC = "Anthropic"
    GOOGLE = "Google"


provider_default_models: dict[LlmProvider, str] = {
    LlmProvider.OLLAMA: "llama3.1:8b",
    LlmProvider.OPENAI: "gpt-4o-mini",
    LlmProvider.GROQ: "llama3-70b-8192",
    LlmProvider.ANTHROPIC: "claude-3-5-sonnet-20240620",
    LlmProvider.GOOGLE: "gemini-1.5-pro-exp-0827",
}

provider_env_key_names: dict[LlmProvider, str] = {
    LlmProvider.OLLAMA: "",
    LlmProvider.OPENAI: "OPENAI_API_KEY",
    LlmProvider.GROQ: "GROQ_API_KEY",
    LlmProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LlmProvider.GOOGLE: "GOOGLE_API_KEY",
}


llm_provider_types: list[LlmProvider] = list(LlmProvider)
provider_select_options: list[tuple[str, LlmProvider]] = [
    (
        p,
        LlmProvider(p),
    )
    for p in llm_provider_types
]


def get_llm_provider_from_str(llm_provider_str: str) -> LlmProvider:
    """Get the LLMProvider given a string matching one of its values."""
    for llm_provider in LlmProvider:
        if llm_provider.value == llm_provider_str:
            return llm_provider
    raise ValueError(f"Invalid LLM provider: {llm_provider_str}")
