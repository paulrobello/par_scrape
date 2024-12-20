"""Callback Handler that prints to std out."""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.load.serializable import Serializable
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.tracers.context import register_configure_hook
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from .llm_config import LlmConfig, llm_run_manager
from .pricing_lookup import PricingDisplay, accumulate_cost, get_api_call_cost, mk_usage_metadata, show_llm_cost

console = Console(stderr=True)


class ParAICallbackHandler(BaseCallbackHandler, Serializable):
    """Callback Handler that tracks OpenAI info."""

    llm_config: LlmConfig | None = None
    show_prompts: bool = False
    show_end: bool = False
    show_tool_calls: bool = False

    def __init__(
        self,
        *,
        llm_config: LlmConfig | None = None,
        show_prompts: bool = False,
        show_end: bool = False,
        show_tool_calls: bool = False,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._usage_metadata = {}
        self.llm_config = llm_config
        self.show_prompts = show_prompts
        self.show_end = show_end
        self.show_tool_calls = show_tool_calls

    def __repr__(self) -> str:
        with self._lock:
            return self._usage_metadata.__repr__()

    @property
    def always_verbose(self) -> bool:
        """Whether to call verbose callbacks even if verbose is False."""
        return True

    @classmethod
    def is_lc_serializable(cls) -> bool:
        """Return whether this model can be serialized by Langchain."""
        return False

    @property
    def usage_metadata(self) -> dict[str, dict[str, int | float]]:
        """Get thread-safe copy of usage metadata."""
        with self._lock:
            return deepcopy(self._usage_metadata)

    def get_usage_metadata(self, model_name: str) -> dict[str, int | float]:
        """Get usage metadata for model_name. Create if not found."""
        if model_name not in self._usage_metadata:
            self._usage_metadata[model_name] = mk_usage_metadata()
        return self._usage_metadata[model_name]

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Print out the prompts."""
        if self.show_prompts:
            console.print(Panel(f"Prompt: {prompts[0]}", title="Prompt"))

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Print out the token."""
        pass

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Collect token usage."""

        if self.show_end:
            console.print(Panel(Pretty(response), title="LLM END"))
            console.print(Panel(Pretty(kwargs), title="LLM END KWARGS"))

        try:
            generation = response.generations[0][0]
        except IndexError:
            generation = None

        llm_config: LlmConfig | None = self.llm_config
        if "tags" in kwargs:
            for tag in reversed(kwargs["tags"]):
                if tag.startswith("config_id="):
                    config_id = tag[len("config_id=") :]
                    config = llm_run_manager.get_config(config_id)
                    llm_config = config[1] if config else None
                    break

        if not llm_config:
            console.print(
                "[yellow]Warning: config_id not found in on_llm_end did you forget to set a RunnableConfig?[/yellow]"
            )
        else:
            # update shared state behind lock
            with self._lock:
                usage_metadata = self.get_usage_metadata(llm_config.model_name)
                if isinstance(generation, ChatGeneration):
                    if hasattr(generation.message, "tool_calls"):
                        usage_metadata["tool_call_count"] += len(generation.message.tool_calls)  # type: ignore
                    accumulate_cost(generation.message, usage_metadata)
                else:
                    if response.llm_output is None:
                        return None
                    if "token_usage" not in response.llm_output:
                        usage_metadata["successful_requests"] += 1
                        return None
                    accumulate_cost(response.llm_output, usage_metadata)
                usage_metadata["total_cost"] += get_api_call_cost(llm_config, usage_metadata)
                usage_metadata["successful_requests"] += 1
                # self._usage_metadata[llm_config.model_name] = usage_metadata

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run when the tool starts running."""
        if not self.show_tool_calls:
            return
        console.print(Panel(Pretty(inputs), title=f"Tool Call: {serialized['name']}"))

    def __copy__(self) -> "ParAICallbackHandler":
        """Return a copy of the callback handler."""
        return self

    def __deepcopy__(self, memo: Any) -> "ParAICallbackHandler":
        """Return a deep copy of the callback handler."""
        return self

    def safe_metadata(self) -> dict[str, dict[str, int | float]]:
        with self._lock:
            return deepcopy(self._usage_metadata)


parai_callback_var: ContextVar[ParAICallbackHandler | None] = ContextVar("parai_callback", default=None)

register_configure_hook(parai_callback_var, True)


@contextmanager
def get_parai_callback(
    llm_config: LlmConfig | None = None,
    *,
    show_prompts: bool = False,
    show_end: bool = False,
    show_pricing: PricingDisplay = PricingDisplay.NONE,
    show_tool_calls: bool = False,
) -> Generator[ParAICallbackHandler, None, None]:
    """Get the llm callback handler in a context manager which exposes token / cost and debug information.

    Args:
        llm_config (LlmConfig): The LLM config.
        show_prompts (bool, optional): Whether to show prompts. Defaults to False.
        show_end (bool, optional): Whether to show end. Defaults to False.
        show_pricing (PricingDisplay, optional): Whether to show pricing. Defaults to PricingDisplay.NONE.
        show_tool_calls (bool, optional): Whether to show tool calls. Defaults to False.

    Returns:
        ParAICallbackHandler: The LLM callback handler.

    Example:
        >>> with get_parai_callback() as cb:
        ...     # Use the LLM callback handler
    """
    cb = ParAICallbackHandler(
        llm_config=llm_config, show_prompts=show_prompts, show_end=show_end, show_tool_calls=show_tool_calls
    )
    parai_callback_var.set(cb)
    yield cb
    show_llm_cost(cb.usage_metadata, show_pricing=show_pricing)
    parai_callback_var.set(None)
