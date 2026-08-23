# Self-Healing Database

An AI-assisted system for diagnosing PostgreSQL errors: it doesn't just log failures, it explains them and suggests fixes.

## Overview

The Self-Healing Database Backend is a full-stack error-handling system for PostgreSQL. Instead of just printing errors to a terminal or a log file, it uses an LLM and vector search to:

- Log structured metadata about every error
- Generate a plain-English explanation and a suggested fix
- Alert developers in real time via Slack
- Let users ask follow-up questions through a chatbot for recurring or unresolved issues

## Why This Project

Most backend systems are reactive — they crash, log an error, and leave the debugging to a human. This project explores a more proactive approach:

- Categorizes errors deterministically via rule-based logic, not the LLM
- Learns from past incidents using vector search (FAISS), with a calibrated relevance threshold so irrelevant history isn't forced into context
- Provides an interactive chatbot for deeper exploration, grounded in live error logs and database stats
- Sends Slack alerts with severity levels and AI-generated fix suggestions

## System Architecture

```mermaid
graph TD
    A[Client] --> B[Application Layer<br/>Frontend + Backend]
    B --> C[View / Add Records]
    B --> D[DBMS<br/>PostgreSQL]
    B --> E[Error Logger]
    D --> E
    E --> F[Vector DB<br/>FAISS]
    F --> G[Embedded error msg]
    F --> H[LLM API<br/>OpenAI GPT-3.5]
    H --> I[Explain this error]
    H --> J[Slack Alert<br/>Notification & Fix]
    
    style A fill:#e1f5fe
    style B fill:#f3e5f5
    style D fill:#e8f5e8
    style E fill:#fff3e0
    style F fill:#fce4ec
    style H fill:#e0f2f1
    style J fill:#f1f8e9
```

### Pipeline Flow

1. **Set up the application** (frontend + backend) connected to PostgreSQL
2. **Handle database operations** (view/add) and use error loggers to catch real-time errors
3. **Embed** the error message and store it in a vector DB
4. **Wrap** the error in a category-specific instructional prompt, re-embed it as the retrieval query, and compare it against stored vectors using a calibrated similarity threshold
5. **Use an LLM** to convert the technical error into a plain-English explanation and suggested fix, grounded in relevant history when it exists
6. **Send the response to Slack**, with severity assigned separately via deterministic rules

### Core Capabilities

| Feature | Description |
|---|---|
| AI-powered debugging | GPT-3.5 interprets and explains database errors with category-specific prompts |
| LangChain + FAISS integration | Retrieves similar past errors, filtered by a calibrated relevance threshold |
| Error logging | Logs detailed error metadata to PostgreSQL with rule-based categorization |
| Slack notifications | Real-time alerts with severity levels and AI-generated analysis |
| Chatbot | Read-only database queries (SELECT-only) plus context-aware responses |
| Web frontend | Flask + vanilla JS interface with live database and error statistics |
| Error categorization | 7 error types with severity levels and auto-fixable indicators |
| Database analytics | Live dashboard with employee/error counts, severity breakdown, and a read-only SQL query interface |

### Built With

- **Backend**: Flask, psycopg2, PostgreSQL
- **AI stack**: OpenAI GPT-3.5-turbo, `text-embedding-3-small`, LangChain, FAISS
- **Frontend**: Flask templates (HTML/CSS/vanilla JS), no build step
- **Monitoring**: Slack webhooks
- **Architecture**: Modular, REST API-based

## Use Cases

This was built as a personal project to work through the full mechanics of a RAG pipeline end to end — embeddings, retrieval scoring, prompt construction, and where each part can silently fail — applied to a concrete problem (database error triage) rather than a toy example. It's not deployed to production and doesn't handle live traffic.

## Future Enhancements

**Completed:**
- Migrated from Streamlit to a single Flask + vanilla JS frontend (removed two duplicate Streamlit implementations)
- Smart error categorization with expert-level responses
- Read-only database query interface, restricted to SELECT statements
- Enhanced Slack notifications with severity levels
- Live error-log dashboard with severity, category, and auto-fixable stats
- Calibrated similarity-threshold filtering so RAG retrieval falls back to the LLM's own knowledge on novel errors instead of forcing irrelevant context
- Fixed a stored XSS vulnerability in the employee records table

**Planned:**
- Auto-recovery: automatic retry logic for transient errors, with LLM-proposed fixes gated behind a PR for human review rather than auto-applied
- Health monitoring: system metrics dashboard with alerts
- Error analytics: trend analysis and predictive insights
- Hardened SQL query validation (the current SELECT-only check is a keyword-based guard, not a real parser)
- Docker deployment: containerized deployment with docker-compose

## Debugging & Issue Resolution

### Real-World Problem: Cascading Database Timeouts

**The Issue:**
During development, cascading timeout errors were initially misdiagnosed as missing database indexes. The system was actually experiencing:
- Connection pool exhaustion
- Silent row lock contention
- Cascading failures across multiple endpoints

**Debugging Process:**

1. **Local reproduction:**
   ```bash
   python3 db_app.py
   # Trigger multiple concurrent requests to cause lock contention
   ```

2. **Added monitoring and tracing:**
   ```python
   # Set lock timeout to prevent long waits
   cur.execute("SET lock_timeout = '5s';")
   
   # Enhanced error logging with context
   INSERT INTO error_logs (error_code, error_message, source, created_at)
   VALUES ('LOCK_CONTENTION', error_msg, 'add_employee', NOW());
   ```

3. **Root cause analysis:**
   - **Problem**: Background processes holding row locks too long
   - **Symptom**: Connection pool starvation causing timeouts
   - **Impact**: Initially misdiagnosed as an indexing issue

4. **Solution implemented:**
   - Lock timeout configuration (`SET lock_timeout = '5s'`)
   - Enhanced error categorization for lock contention

**Key Learnings:**
- Reproduce issues locally before fixing
- Monitor connection pool behavior during debugging
- Use error categorization to prevent alert storms

**Tools Used:**
- PostgreSQL query logs
- Flask error handlers
- Slack notifications for real-time monitoring
- FAISS vector store for error pattern matching

### Real-World Problem: RAG Retrieval Had No Relevance Threshold

**The Issue:**
The FAISS retriever always returned the top-4 nearest vectors regardless of how similar they actually were. For a genuinely novel error type, the LLM still received 4 "similar" historical errors as context even when none of them were actually related — risking a misleading fix instead of a clean, knowledge-based answer.

**Debugging Process:**
1. **Empirical calibration:** embedded a known near-duplicate error alongside a completely unrelated query and compared the raw FAISS distance scores:
   ```python
   vectorstore.similarity_search_with_score(query, k=4)
   # Related errors:   distance ~ 0.53
   # Unrelated text:   distance ~ 1.85-2.05
   ```
2. **Root cause:** LangChain's default `as_retriever()` has no relevance/score threshold — it always returns the k nearest vectors, no matter how far away they are.

**Solution Implemented:**
- Replaced the retriever with a custom step (`retrieve_with_threshold`) that discards any match with a distance above `1.0`, a cutoff chosen from the empirical gap between the two clusters above.
- Updated the prompt so that when nothing passes the threshold, the LLM is explicitly told to answer from its own knowledge instead of refusing.

**Key Learnings:**
- Default retriever settings don't fail loudly — "no good match" silently becomes "return the 4 least-bad matches," which quietly degrades output quality.
- Calibrating thresholds empirically, rather than guessing a number, makes the cutoff defensible and tunable later.

## Developer's Note

This project was built to understand every component deeply, not just to produce a working app — from PostgreSQL locking to vector retrieval and LLM behavior. It's a personal/portfolio project, not a production system.

## Quickstart

### Prerequisites
- Python 3.10+
- PostgreSQL database
- OpenAI API key
- Slack webhook (optional)

### Setup

1) **Create database and tables:**
```sql
CREATE DATABASE self_healing_app;
\c self_healing_app;

CREATE TABLE employee (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  department TEXT,
  joining_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE error_logs (
  id SERIAL PRIMARY KEY,
  error_code TEXT,
  error_message TEXT NOT NULL,
  source TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  severity TEXT -- reserved; severity is computed live, not currently persisted here
);
```

2) **Configure environment:**
```bash
# Create .env file
OPENAI_API_KEY=sk-your-key-here
SLACK_WEBHOOK=https://hooks.slack.com/services/xxx/yyy/zzz
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/self_healing_app
CHATBOT_URL=http://127.0.0.1:5000/chat
```

3) **Install and run:**
```bash
pip install -r requirements.txt
python3 db_app.py
```

4) **Access the application:**
- **Dashboard**: `http://127.0.0.1:5000/` — view/add employees, live error diagnostics
- **Chatbot**: `http://127.0.0.1:5000/chat` — AI assistant with database queries (also linked directly from each Slack alert)

## Key Features

### Smart Error Handling
- **7 error categories**: DUPLICATE_DATA, CONNECTION_ISSUE, LOCK_CONTENTION, PERMISSION_ERROR, QUERY_SYNTAX, CONSTRAINT_VIOLATION, RESOURCE_EXHAUSTION
- **Severity levels**: LOW, MEDIUM, HIGH — assigned deterministically via keyword rules, not the LLM
- **Auto-fixable detection**: flags errors that could plausibly be resolved automatically (not yet wired to any automated action)

### Intelligent Chatbot
- **Real-time database context**: automatically includes current stats and recent error logs
- **Read-only query interface**: restricted to SELECT statements via a keyword-based guard
- **Category-specific prompts**: tailored instructions per error category
- **Accessed via Slack**: not exposed as a primary nav item on the dashboard — reached through the "Open the Self-Healing Chatbot" link in each Slack alert, keeping the main UI focused on data entry and diagnostics

### Slack Integration
- Structured alerts with severity indicators
- AI-generated explanations and actionable recommendations
- Direct link to the chatbot for deeper troubleshooting
