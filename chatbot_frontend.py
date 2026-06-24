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

Write SQL to answer this question using live data from employee and/or error_logs.
Return ONLY valid JSON:
{{"queries": ["SELECT ...", "..."]}}

Rules:
- 1 to 3 SELECT queries only
- use created_at for time filtering/sorting on error_logs
- for "recent errors", select id, error_code, severity, source, created_at, error_message (no unnecessary filters)
- for duplicate-email frequency, extract email from error_message (not from source)
- for lock issues, filter error_message or error_code
- never invent column names
{extra}
"""

SYNTHESIS_PROMPT = """{system_context}

Conversation:
{history}

User question: {question}

You already ran SQL for the user. Present the answer now.

Queries executed:
{queries}

Raw results:
{results}

Write the final answer for the user.

REQUIRED:
- answer directly using the result rows (counts, emails, error codes, dates)
- when multiple rows are returned, list each row with its key fields
- explain cause and fix when debugging
- be concise and specific

FORBIDDEN:
- do NOT tell the user to run SQL
- do NOT say "if you run a query" or "you can run"
- do NOT say data is unavailable when results are shown above
- do NOT give generic monitoring advice without evidence from results
- do NOT include SQL blocks unless briefly noting what you already checked
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
                history=history,
                question=question,
                queries="\n".join(queries),
                results=bundle_results(queries, results),
            )
            + "\n\nRewrite without telling the user to run SQL. Present the findings directly."
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
        return (
            "I tried to query the database but couldn't retrieve results for that question. "
            f"Details: {'; '.join(results)}"
        )

    return synthesize_response(prompt, history, executed, results)


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
