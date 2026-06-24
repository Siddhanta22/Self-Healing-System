#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
streamlit run chatbot_frontend.py --server.port 8502
