#!/usr/bin/env bash

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    python3 -m venv "$SCRIPT_DIR/venv"
fi

source "$SCRIPT_DIR/venv/bin/activate"

pip install -r "$SCRIPT_DIR/requirements.txt"

python "$SCRIPT_DIR/__init__.py"
