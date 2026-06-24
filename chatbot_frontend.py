import json
import os
import re

import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.tools.sql_database.tool import QuerySQLDataBaseTool

load_dotenv()

llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0.1,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

db = SQLDatabase.from_uri(
    os.getenv("DATABASE_URL"),
    include_tables=["employee", "error_logs"],
    sample_rows_in_table_info=3,
)
query_tool = QuerySQLDataBaseTool(db=db)

SCHEMA_INFO = db.get_table_info()

SYSTEM_CONTEXT = f"""You are a Self-Healing Database debugging assistant.

Database schema and sample rows:
{SCHEMA_INFO}

Critical facts:
- employee columns: id, name, email, department, joining_date
- error_logs columns: id, error_code, error_message, source, created_at, severity
- employee.email is UNIQUE
- error_logs.created_at is the time column (NO "timestamp" column)
- error_logs has NO email column
- duplicate emails appear inside error_message like: Key (email)=(user@domain.com)
- extract email from error_message with:
  substring(error_message from 'Key \\(email\\)=\\(([^)]+)\\)')
- there is NO salary column
- common error_code values: DUPLICATE_KEY, LOCK_NOT_AVAILABLE, UNEXPECTED_EXCEPTION
- this app writes errors from the add_employee flow
- PostgreSQL lock issues often appear as LOCK_NOT_AVAILABLE or messages containing "lock"
- "current transaction is aborted" usually means a prior statement failed and the transaction needs ROLLBACK before retrying
"""

PLAYBOOK = """
Debugging playbooks (use when user asks what to do, even if logs are empty):
- Table lock / lock timeout: retry after a few seconds; end stuck transactions (ROLLBACK); avoid long open transactions; check concurrent writes to employee; this backend sets lock_timeout=5s.
- Duplicate email: email must be unique in employee; use a different email or update the existing row; check error_logs + employee for the conflicting address.
- Aborted transaction: run ROLLBACK in the session; fix the first failing statement; retry the operation.
- Foreign key / constraint: verify referenced rows exist before insert; align app validation with DB constraints.
"""

GREETING_PROMPT = """{system_context}

Conversation:
{history}

User: {question}

Reply briefly and helpfully. Do not mention SQL or queries.
"""

PLANNER_PROMPT = """{system_context}

Conversation:
{history}

User question: {question}

Write SQL to gather evidence needed to answer the question.
Return ONLY valid JSON:
{{"queries": ["SELECT ...", "..."]}}

Rules:
- 1 to 3 SELECT queries only; every query must be directly relevant to the user's question
- use created_at for time filtering/sorting on error_logs
- for "what do I do if X" / troubleshooting: first check error_logs for X-related rows (error_code and/or error_message)
- for "recent errors", select id, error_code, severity, source, created_at, error_message (no unnecessary filters)
- for duplicate-email questions, extract email from error_message (not from source)
- for lock questions, filter error_code = 'LOCK_NOT_AVAILABLE' OR error_message ILIKE '%lock%'
- do NOT query unrelated error types (e.g. do not fetch duplicate-key stats when user asks about locks)
- never invent column names
{extra}
"""

SYNTHESIS_PROMPT = """{system_context}

{playbook}

Conversation:
{history}

User question: {question}

You already ran SQL for the user. Write the final answer.

Queries executed:
{queries}

Raw results:
{results}

Structure the answer with these sections (omit empty ones):

**What I found in your database**
- Only discuss query results relevant to the user's question
- Ignore unrelated rows even if they were returned
- If no matching rows: say clearly that no relevant errors were found in error_logs (or employee) for this scenario

**What it means**
- Explain the situation in plain English using the evidence above

**What to do**
- Always give practical fix/debugging steps for the scenario the user asked about
- If logs show no matching errors, say that and still explain how to handle/prevent the issue in this app
- Tie advice to this schema (employee, error_logs, add_employee) when helpful

REQUIRED:
- combine live DB evidence with actionable guidance
- when multiple relevant rows exist, list key fields (id, error_code, created_at, message snippet)
- be concise and specific

FORBIDDEN:
- do NOT tell the user to run SQL
- do NOT pivot to unrelated errors (e.g. duplicate-key stats when user asked about locks)
- do NOT say "if you run a query" or "you can run"
- do NOT give vague monitoring-only advice without concrete steps
"""

FIX_SQL_PROMPT = """{system_context}

Failed SQL:
{sql}

Error:
{error}

Return ONLY valid JSON:
{{"queries": ["corrected SELECT ..."]}}
"""

SIMPLE_GREETINGS = {
    "hi", "hello", "hey", "hola", "thanks", "thank you",
    "good morning", "good afternoon", "good evening",
}


def format_history(messages: list[tuple[str, str]], limit: int = 8) -> str:
    if not messages:
        return "(none)"
    lines = []
    for role, msg in messages[-limit:]:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {msg}")
    return "\n".join(lines)


def parse_json_block(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def is_simple_greeting(prompt: str) -> bool:
    text = prompt.strip().lower().rstrip("?!.")
    return text in SIMPLE_GREETINGS


def is_safe_sql(sql: str) -> bool:
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return False
    forbidden = r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b"
    return re.search(forbidden, normalized) is None


def plan_queries(question: str, history: str, extra: str = "") -> list[str]:
    raw = llm.invoke(
        PLANNER_PROMPT.format(
            system_context=SYSTEM_CONTEXT,
            history=history,
            question=question,
            extra=extra,
        )
    ).content
    plan = parse_json_block(raw)
    return [q for q in plan.get("queries", []) if isinstance(q, str) and q.strip()]


def run_queries(queries: list[str]) -> tuple[list[str], list[str]]:
    executed = []
    results = []

    for sql in queries[:3]:
        if not is_safe_sql(sql):
            results.append(f"Rejected unsafe SQL: {sql}")
            continue

        current_sql = sql
        for attempt in range(2):
            try:
                output = query_tool.run(current_sql)
                executed.append(current_sql)
                results.append(output if output else "(no rows returned)")
                break
            except Exception as exc:
                if attempt == 0:
                    fix = llm.invoke(
                        FIX_SQL_PROMPT.format(
                            system_context=SYSTEM_CONTEXT,
                            sql=current_sql,
                            error=str(exc),
                        )
                    ).content
                    fixed = parse_json_block(fix).get("queries", [])
                    if fixed and is_safe_sql(fixed[0]):
                        current_sql = fixed[0]
                        continue
                results.append(f"SQL error: {exc}")
                break

    return executed, results


def bundle_results(queries: list[str], results: list[str]) -> str:
    chunks = []
    for i, (query, result) in enumerate(zip(queries, results), start=1):
        chunks.append(f"--- Result {i} ---\nSQL: {query}\nData: {result}")
    return "\n\n".join(chunks) if chunks else "(no successful queries)"


def synthesize_response(
    question: str, history: str, queries: list[str], results: list[str]
) -> str:
    answer = llm.invoke(
        SYNTHESIS_PROMPT.format(
            system_context=SYSTEM_CONTEXT,
            playbook=PLAYBOOK,
            history=history,
            question=question,
            queries="\n".join(queries),
            results=bundle_results(queries, results),
        )
    ).content

    if re.search(r"\b(run this query|you can run|if you run|try running|execute the following)\b", answer, re.I):
        answer = llm.invoke(
            SYNTHESIS_PROMPT.format(
                system_context=SYSTEM_CONTEXT,
                playbook=PLAYBOOK,
                history=history,
                question=question,
                queries="\n".join(queries),
                results=bundle_results(queries, results),
            )
            + "\n\nRewrite without telling the user to run SQL. Present findings and fix steps directly."
        ).content

    return answer


def get_reply(prompt: str, history_messages: list[tuple[str, str]]) -> str:
    history = format_history(history_messages)

    if is_simple_greeting(prompt):
        return llm.invoke(
            GREETING_PROMPT.format(
                system_context=SYSTEM_CONTEXT,
                history=history,
                question=prompt,
            )
        ).content

    queries = plan_queries(prompt, history)
    if not queries:
        queries = plan_queries(
            prompt,
            history,
            extra="- you MUST return at least one SELECT query",
        )

    executed, results = run_queries(queries)

    if not executed:
        retry_queries = plan_queries(
            prompt,
            history,
            extra=(
                "- previous queries failed\n"
                f"- errors: {results}\n"
                "- return corrected SELECT queries only"
            ),
        )
        if retry_queries:
            executed, results = run_queries(retry_queries)

    if not executed:
        return synthesize_advisory_response(prompt, history, results)

    return synthesize_response(prompt, history, executed, results)


def synthesize_advisory_response(
    question: str, history: str, errors: list[str]
) -> str:
    """Answer with playbook guidance when SQL could not be executed."""
    return llm.invoke(
        f"""{SYSTEM_CONTEXT}

{PLAYBOOK}

Conversation:
{history}

User question: {question}

Database query attempt failed: {'; '.join(errors)}

Still help the user with:
1. What the issue usually means in PostgreSQL / this app
2. Practical steps to fix or prevent it
3. What to check in error_logs or employee when the database is available again

Do not tell the user to run SQL themselves.
"""
    ).content


st.set_page_config(page_title="Self-Healing Chatbot", page_icon="💬")
st.title("💬 Self-Healing Assistant")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

for role, msg in st.session_state["messages"]:
    with st.chat_message(role):
        st.markdown(msg)

if prompt := st.chat_input("Ask about your error …"):
    st.session_state["messages"].append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking…"):
                reply = get_reply(prompt, st.session_state["messages"][:-1])
        except Exception as exc:
            reply = f"❌ Assistant error: {exc}"

        st.markdown(reply)
        st.session_state["messages"].append(("assistant", reply))
