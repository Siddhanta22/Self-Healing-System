# 🔧 Self-Healing Database Backend

A Flask-based backend system that automatically detects, logs, and provides AI-powered solutions for database errors. Built with modern technologies including LangChain, OpenAI, and FAISS for intelligent error resolution.

## ✨ Features

- **🤖 AI-Powered Error Resolution**: Uses LangChain + OpenAI to provide intelligent solutions for database errors
- **📊 Real-time Error Logging**: Automatically logs errors to PostgreSQL with detailed metadata
- **🔍 Vector Search**: FAISS vector database for intelligent error retrieval and similarity matching
- **📱 Real-time Alerts**: Slack notifications for critical errors with AI-generated explanations
- **🌐 Web Interface**: Streamlit frontend for easy interaction and error management
- **💬 Interactive Chatbot**: AI-powered assistant for error troubleshooting

## 🛠️ Tech Stack

- **Backend**: Flask, PostgreSQL, psycopg2
- **AI/ML**: LangChain, OpenAI GPT-3.5-turbo, OpenAI Embeddings
- **Vector Database**: FAISS
- **Frontend**: Streamlit
- **Monitoring**: Slack Webhooks
- **API**: RESTful endpoints with JSON responses

## 🚀 Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment variables (see `.env.example`)
3. Run the backend: `python db_app.py`
4. Run the frontend: `streamlit run frontend_streamlit.py`
5. Run the chatbot: `streamlit run chatbot_frontend.py`

## 🔧 How It Works

1. **Error Detection**: When a database error occurs, it's automatically caught and logged
2. **AI Analysis**: The error message is processed through LangChain and OpenAI
3. **Vector Storage**: Error patterns are stored in FAISS for future reference
4. **Smart Retrieval**: Similar errors are retrieved to provide context-aware solutions
5. **Real-time Alerts**: Slack notifications are sent with AI-generated explanations
6. **Interactive Help**: Users can chat with the AI assistant for additional support

## 🎯 Key Achievements

- Implemented comprehensive error handling with automatic logging
- Integrated AI/ML for intelligent error resolution
- Built real-time monitoring and alerting system
- Created full-stack application with modern web interface
- Demonstrated proficiency in multiple technologies and frameworks

---

**Built with ❤️ by Siddhanta Mohanty**

self-healing-system/
│
├── db_app.py               # Flask backend with error handling
├── chatbot_frontend.py     # Chatbot frontend (Streamlit)
├── frontend_streamlit.py   # Dashboard to view/add employees
├── notify_slack.py         # Slack notification helper
├── llm.py                  # LangChain + OpenAI integration
├── error_vectordb.py       # FAISS vector store functions
├── requirements.txt        # Dependency list
├── .env.example            # Environment variable template
├── README.md               # Project documentation
└── faiss_index/            # Vector DB files

