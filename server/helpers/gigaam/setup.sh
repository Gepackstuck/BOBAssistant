#!/bin/sh
set -eu
cd "$(dirname "$0")"
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch numpy hydra-core omegaconf sentencepiece pyannote-audio "transformers==4.57.1"
echo "Готово. Модель скачается с Hugging Face (ai-sage/GigaAM-v3, ревизия rnnt) при первом запуске."
