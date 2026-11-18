import json
from dataclasses import dataclass
from typing import Any, Callable

from . import calc, clock, search, weather, wiki


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


def build_registry(cfg: dict, memory, music, planner, home, tvcontrol) -> Registry:
    from ..memory import specs as memory_specs
    from ..music import specs as music_specs
    from ..planner import specs as planner_specs
    from ..home import specs as home_specs
    from ..tvcontrol import specs as tv_specs
    return Registry([
        Tool(**clock.spec(cfg)),
        Tool(**weather.spec(cfg)),
        Tool(**calc.spec()),
        Tool(**search.spec()),
        Tool(**wiki.spec()),
        *[Tool(**spec) for spec in memory_specs(memory)],
        *[Tool(**spec) for spec in music_specs(music)],
        *[Tool(**spec) for spec in planner_specs(planner)],
        *[Tool(**spec) for spec in tv_specs(tvcontrol)],
        *([Tool(**spec) for spec in home_specs(home)] if home.connected() else []),
    ])
