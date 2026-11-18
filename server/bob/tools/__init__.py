import json
from dataclasses import dataclass
from typing import Any, Callable

from . import calc, clock, search, weather


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], str]


class Registry:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}

    def specs(self) -> list[Tool]:
        return list(self.tools.values())

    def call(self, name: str, arguments: dict[str, Any] | str) -> tuple[str, bool]:
        tool = self.tools.get(name)
        if tool is None:
            return f"Нет инструмента {name}", True
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            result, failed = tool.run(args or {}), False
        except Exception as error:
            result, failed = f"Ошибка: {error}", True
        print(f"   🔧 {name}({arguments or ''}) → {result[:160]}")
        return result, failed


def build_registry(cfg: dict, memory) -> Registry:
    from ..memory import specs as memory_specs
    return Registry([
        Tool(**clock.spec(cfg)),
        Tool(**weather.spec(cfg)),
        Tool(**calc.spec()),
        Tool(**search.spec()),
        *[Tool(**spec) for spec in memory_specs(memory)],
    ])
