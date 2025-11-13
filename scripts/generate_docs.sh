#!/usr/bin/env bash
set -euo pipefail

# activate venv if you use one, or ensure PYTHONPATH
# Example: PYTHONPATH=src ./scripts/generate_docs.sh

OUT_DIR=docs
mkdir -p "${OUT_DIR}"

echo "Generating docs for examples.simple_app.app:AppSettings -> ${OUT_DIR}/app_settings.md"
dco docs examples.simple_app.app:AppSettings --out "${OUT_DIR}/app_settings.md" --title "AppSettings Configuration"

echo "Done. Open ${OUT_DIR}/app_settings.md"
