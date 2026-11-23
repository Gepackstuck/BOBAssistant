import json
import sys
from pathlib import Path

from gigachat_audio_mlx.cli import TASK_PROMPTS
from gigachat_audio_mlx.runtime import GigaChatAudioRuntime

MODEL = Path(__file__).parent / "model"


def main() -> None:
    runtime = GigaChatAudioRuntime.load(MODEL, verify_hashes=False)
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        prompt = request.get("prompt") or TASK_PROMPTS["transcribe"]
        messages = [{"role": "user", "content": [{"type": "audio", "path": request["wav"]}, {"type": "text", "text": f"\n{prompt}"}]}]
        try:
            result = runtime.generate(messages, max_tokens=request.get("max_tokens", 300), temperature=0.0, top_p=1.0)
        except Exception as error:
            print(json.dumps({"error": str(error)}), flush=True)
            continue
        print(json.dumps({"text": result.text}, ensure_ascii=False), flush=True)


main()
