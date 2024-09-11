"""Models for rag related tasks."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from langchain._api import LangChainDeprecationWarning
from langchain_anthropic import ChatAnthropic
from langchain_community.llms.ollama import Ollama
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models import BaseLanguageModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai import GoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAI
from langchain_openai import OpenAIEmbeddings


from par_scrape.lib.llm_providers import LlmProvider
from par_scrape.lib.par_ollama_embeddings import ParOllamaEmbeddings


warnings.simplefilter("ignore", category=LangChainDeprecationWarning)

ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class LlmMode(str, Enum):
    """LLM mode types."""

    BASE = "Base"
    CHAT = "Chat"
    EMBEDDINGS = "Embeddings"


llm_modes: list[LlmMode] = list(LlmMode)


@dataclass
class LlmConfig:
    """Configuration for Llm."""

    provider: LlmProvider
    model_name: str
    mode: LlmMode = LlmMode.CHAT
    temperature: float = 0.5
    streaming: bool = False
    base_url: Optional[str] = None
    class_name: str = "LlmConfig"

    def to_json(self) -> dict:
        """Return dict for use with json"""
        return {
            "class_name": self.__class__.__name__,
            "provider": self.provider,
            "model_name": self.model_name,
            "mode": self.mode,
            "temperature": self.temperature,
            "streaming": self.streaming,
            "base_url": self.base_url,
        }

    @staticmethod
    def from_json(data: dict) -> LlmConfig:
        """Create instance from json data"""
        if data["class_name"] != "LlmConfig":
            raise ValueError(f"Invalid config class: {data['class_name']}")
        del data["class_name"]
        return LlmConfig(**data)

    def clone(self) -> LlmConfig:
        """Create a clone of the LlmConfig."""
        return LlmConfig(
            provider=self.provider,
            model_name=self.model_name,
            mode=self.mode,
            temperature=self.temperature,
            streaming=self.streaming,
            base_url=self.base_url,
        )

    # pylint: disable=too-many-return-statements,too-many-branches
    def _build_llm(self) -> BaseLanguageModel | BaseChatModel | Embeddings:
        """Build the LLM."""
        if self.provider == LlmProvider.OLLAMA:
            if self.mode == LlmMode.BASE:
                return Ollama(
                    model=self.model_name,
                    temperature=self.temperature,
                    base_url=self.base_url or ollama_host,
                )
            if self.mode == LlmMode.CHAT:
                return ChatOllama(
                    model=self.model_name,
                    temperature=self.temperature,
                    base_url=self.base_url or ollama_host,
                )
            if self.mode == LlmMode.EMBEDDINGS:
                return ParOllamaEmbeddings(
                    ollama_host=self.base_url or ollama_host, model=self.model_name
                )
        elif self.provider == LlmProvider.OPENAI:
            if self.mode == LlmMode.BASE:
                return OpenAI(
                    model=self.model_name,
                    temperature=self.temperature,
                    streaming=self.streaming,
                    base_url=self.base_url,
                )
            if self.mode == LlmMode.CHAT:
                return ChatOpenAI(
                    model=self.model_name,
                    temperature=self.temperature,
                    streaming=self.streaming,
                    base_url=self.base_url,
                )
            if self.mode == LlmMode.EMBEDDINGS:
                return OpenAIEmbeddings(model=self.model_name)
        elif self.provider == LlmProvider.GROQ:
            if self.mode == LlmMode.BASE:
                raise ValueError(
                    f"{self.provider} provider does not support mode {self.mode}"
                )
            if self.mode == LlmMode.CHAT:
                return ChatGroq(
                    model=self.model_name,
                    temperature=self.temperature,
                    streaming=self.streaming,
                    base_url=self.base_url,
                )  # pyright: ignore [reportCallIssue]
            if self.mode == LlmMode.EMBEDDINGS:
                raise ValueError(
                    f"{self.provider} provider does not support mode {self.mode}"
                )
        elif self.provider == LlmProvider.ANTHROPIC:
            if self.mode == LlmMode.BASE:
                raise ValueError(
                    f"{self.provider} provider does not support mode {self.mode}"
                )
            if self.mode == LlmMode.CHAT:
                return ChatAnthropic(  # pyright: ignore [reportCallIssue]
                    model=self.model_name,  # pyright: ignore [reportCallIssue]
                    temperature=self.temperature,
                    streaming=self.streaming,
                    default_headers={"anthropic-beta": "tools-2024-05-16"},
                    base_url=self.base_url,
                    # max_tokens=8_192,
                )
            if self.mode == LlmMode.EMBEDDINGS:
                raise ValueError(
                    f"{self.provider} provider does not support mode {self.mode}"
                )
        elif self.provider == LlmProvider.GOOGLE:
            if self.mode == LlmMode.BASE:
                return GoogleGenerativeAI(
                    model=self.model_name, temperature=self.temperature
                )
            if self.mode == LlmMode.CHAT:
                return ChatGoogleGenerativeAI(
                    model=self.model_name, temperature=self.temperature
                )
            if self.mode == LlmMode.EMBEDDINGS:
                raise ValueError(
                    f"{self.provider} provider does not support mode {self.mode}"
                )
        raise ValueError(
            f"Invalid LLM provider '{self.provider}' or mode '{self.mode}'"
        )

    def build_llm_model(self) -> BaseLanguageModel:
        """Build the LLM model."""
        llm = self._build_llm()
        if isinstance(llm, BaseLanguageModel):
            return llm
        raise ValueError(f"LLM provider '{self.provider}' does not support base mode.")

    def build_chat_model(self) -> BaseChatModel:
        """Build the chat model."""
        llm = self._build_llm()
        if isinstance(llm, BaseChatModel):
            return llm
        raise ValueError(f"LLM provider '{self.provider}' does not support chat mode.")

    def build_embeddings(self) -> Embeddings:
        """Build the embeddings."""
        llm = self._build_llm()
        if isinstance(llm, Embeddings):
            return llm
        raise ValueError(f"LLM mode '{self.mode}' does not support embeddings.")
