#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
streamlit run db_frontend.py --server.port 8501
