import os

import httpx

from ..tools import Registry


class OpenAiCompat:
    def __init__(self, cfg: dict):
        key_env = cfg.get("api_key_env")
        headers = {"Authorization": f"Bearer {os.environ[key_env]}"} if key_env else {}
        self.client = httpx.Client(base_url=cfg["base_url"].rstrip("/"), headers=headers, timeout=120)
        self.model = cfg["model"]
        self.max_tokens = cfg["max_tokens"]
        self.temperature = cfg["temperature"]
        self.max_rounds = cfg["max_tool_rounds"]

    def new_session(self) -> list:
        return []

    def _tools(self, registry: Registry) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in registry.specs()
        ]

    def _complete(self, messages: list[dict], tools: list[dict] | None) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            **({"tools": tools} if tools else {}),
        }
        response = self.client.post("/chat/completions", json=body)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]

    def reply(self, session: list, system: str, user_text: str, registry: Registry) -> str:
        session.append({"role": "user", "content": user_text})
        tools = self._tools(registry)
        for round_index in range(self.max_rounds + 1):
            message = self._complete(
                [{"role": "system", "content": system}, *session],
                tools if round_index < self.max_rounds else None,
            )
            calls = message.get("tool_calls") or []
            session.append({
                "role": "assistant",
                "content": message.get("content") or "",
                **({"tool_calls": calls} if calls else {}),
            })
            if not calls:
                return (message.get("content") or "").strip()
            session.extend(
                {"role": "tool", "tool_call_id": call.get("id", ""), "content": registry.call(call["function"]["name"], call["function"].get("arguments") or "{}")[0]}
                for call in calls
            )
        return ""

    def warm_up(self) -> None:
        self._complete([{"role": "user", "content": "Привет"}], None)
