from typing import Protocol

from ..tools import Registry


class Llm(Protocol):
    def new_session(self) -> list: ...

    def reply(self, session: list, system: str, user_text: str, registry: Registry) -> str: ...


def make_llm(cfg: dict) -> Llm:
    provider = cfg["provider"]
    if provider == "openai_compat":
        from .openai_compat import OpenAiCompat
        return OpenAiCompat(cfg)
    if provider == "anthropic":
        from .anthropic_api import AnthropicLlm
        return AnthropicLlm(cfg)
    raise ValueError(f"Неизвестный провайдер LLM: {provider}")
