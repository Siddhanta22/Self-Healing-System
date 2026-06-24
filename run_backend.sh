#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python db_app.py
