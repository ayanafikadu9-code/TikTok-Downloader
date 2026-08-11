#!/usr/bin/env sh
# Simple local launcher: loads .env and runs bot.py
set -e

if [ -f .env ]; then
  # export variables from .env (ignores comments)
  export $(grep -v '^#' .env | xargs)
fi

python bot.py
