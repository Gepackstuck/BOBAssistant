import anthropic

from ..tools import Registry


class AnthropicLlm:
    def __init__(self, cfg: dict):
        self.client = anthropic.Anthropic()
        self.model = cfg["model"]
        self.max_tokens = cfg["max_tokens"]
        self.effort = cfg.get("effort", "low")
        self.max_rounds = cfg["max_tool_rounds"]

    def new_session(self) -> list:
        return []

    def _tools(self, registry: Registry) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True}
            for t in registry.specs()
        ]

    def reply(self, session: list, system: str, user_text: str, registry: Registry) -> str:
        session.append({"role": "user", "content": user_text})
        tools = self._tools(registry)
        for _ in range(self.max_rounds + 1):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=tools,
                messages=session,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            session.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return "Не могу с этим помочь."
            if response.stop_reason == "pause_turn":
                continue
            calls = [block for block in response.content if block.type == "tool_use"]
            if not calls:
                return " ".join(block.text for block in response.content if block.type == "text").strip()
            results = [(call, *registry.call(call.name, call.input)) for call in calls]
            session.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": failed}
                    for call, text, failed in results
                ],
            })
        return ""

    def warm_up(self) -> None:
        return None
