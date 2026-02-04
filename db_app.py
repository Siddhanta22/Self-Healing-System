from flask import Flask, request, jsonify, render_template, url_for
import psycopg2
from psycopg2 import errorcodes
import psycopg2.extras
import requests
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from dotenv import load_dotenv   #Loads OpenAI API Key & Slack Webhook from .env
load_dotenv()   # populates os.environ["OPENAI_API_KEY"] from .env
from langchain_openai import OpenAIEmbeddings
import os

CHATBOT_URL = os.getenv("CHATBOT_URL", "http://127.0.0.1:5000/chat")

from flask_cors import CORS
app = Flask(__name__)
CORS(app)

CORS(app, resources={r"/*": {"origins": "*"}})

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

def send_slack_message(message: str):   # Function to send messages to Slack
    webhook_url = SLACK_WEBHOOK
    payload = {"text": message}   #JSON format 
    try:
        print("📣 Sending to Slack…", message)
        requests.post(webhook_url, json=payload)    #Send POST request
    except Exception as e:
        print("Slack webhook failed:", e)

def categorize_error(error_msg: str, error_code: str = "UNKNOWN"):
    """Smart error categorization with pattern matching"""
    error_lower = error_msg.lower()
    
    # Common database patterns
    if "duplicate key" in error_lower or "unique constraint" in error_lower:
        return "DUPLICATE_DATA", "LOW", True
    elif "connection" in error_lower or "timeout" in error_lower or "connection refused" in error_lower:
        return "CONNECTION_ISSUE", "HIGH", True
    elif "lock" in error_lower or "deadlock" in error_lower or "lock not available" in error_lower:
        return "LOCK_CONTENTION", "MEDIUM", False
    elif "permission" in error_lower or "access denied" in error_lower or "insufficient privilege" in error_lower:
        return "PERMISSION_ERROR", "HIGH", False
    elif "syntax" in error_lower or "invalid" in error_lower or "malformed" in error_lower:
        return "QUERY_SYNTAX", "MEDIUM", False
    elif "foreign key" in error_lower or "constraint" in error_lower:
        return "CONSTRAINT_VIOLATION", "MEDIUM", False
    elif "out of memory" in error_lower or "memory" in error_lower:
        return "RESOURCE_EXHAUSTION", "HIGH", False
    else:
        return "UNKNOWN", "MEDIUM", False

def get_category_specific_prompt(category: str, error_msg: str):
    """Provide tailored prompts for different error types"""
    
    prompts = {
        "DUPLICATE_DATA": f"""
        You are a database expert specializing in data integrity. This is a duplicate data error: {error_msg}
        
        Provide a comprehensive response including:
        1. Clear explanation of why this duplicate key violation occurred
        2. Immediate fix options (check existing data, suggest unique values, handle gracefully)
        3. Prevention strategy (input validation, database constraints, application logic)
        4. Business impact assessment and best practices
        5. Code examples for handling duplicates in the application
        
        Be specific and actionable. Focus on both immediate resolution and long-term prevention.
        """,
        
        "CONNECTION_ISSUE": f"""
        You are a database administrator with expertise in infrastructure. This is a connection error: {error_msg}
        
        Provide a detailed analysis including:
        1. Root cause analysis of the connection failure
        2. Immediate troubleshooting steps (check network, credentials, firewall)
        3. Infrastructure recommendations (connection pooling, retry logic, monitoring)
        4. Monitoring and alerting suggestions
        5. Performance optimization tips for database connections
        
        Focus on both immediate resolution and system reliability improvements.
        """,
        
        "LOCK_CONTENTION": f"""
        You are a database performance expert. This is a locking issue: {error_msg}
        
        Provide expert guidance including:
        1. Why locks are happening (concurrent transactions, long-running queries)
        2. Short-term workarounds (retry logic, timeout adjustments)
        3. Long-term optimization strategies (query optimization, indexing, transaction design)
        4. Query performance tips and best practices
        5. Monitoring queries to identify lock patterns
        
        Emphasize both immediate fixes and performance improvements.
        """,
        
        "PERMISSION_ERROR": f"""
        You are a database security expert. This is a permission error: {error_msg}
        
        Provide security-focused guidance including:
        1. Analysis of the permission/access issue
        2. Immediate resolution steps (check user roles, grant permissions)
        3. Security best practices (principle of least privilege, role-based access)
        4. Audit and monitoring recommendations
        5. Long-term security strategy
        
        Focus on both immediate access restoration and security hardening.
        """,
        
        "QUERY_SYNTAX": f"""
        You are a SQL expert. This is a query syntax error: {error_msg}
        
        Provide technical guidance including:
        1. Analysis of the syntax issue
        2. Corrected query examples
        3. Common SQL pitfalls and how to avoid them
        4. Query optimization tips
        5. Best practices for SQL development
        
        Be technical but clear, with practical examples.
        """,
        
        "CONSTRAINT_VIOLATION": f"""
        You are a database design expert. This is a constraint violation: {error_msg}
        
        Provide comprehensive guidance including:
        1. Analysis of the constraint violation
        2. Immediate resolution options
        3. Database design best practices
        4. Data integrity strategies
        5. Application-level validation recommendations
        
        Focus on both immediate fixes and robust data modeling.
        """,
        
        "RESOURCE_EXHAUSTION": f"""
        You are a database performance and infrastructure expert. This is a resource exhaustion error: {error_msg}
        
        Provide expert analysis including:
        1. Root cause analysis of resource exhaustion
        2. Immediate mitigation strategies
        3. Infrastructure scaling recommendations
        4. Query optimization for resource efficiency
        5. Monitoring and alerting for resource usage
        
        Emphasize both immediate relief and long-term scalability.
        """,
        
        "UNKNOWN": f"""
        You are a general database expert. This is an unknown error: {error_msg}
        
        Provide comprehensive guidance including:
        1. General analysis and possible causes
        2. Systematic debugging approach
        3. When to escalate to senior team members
        4. Documentation and logging recommendations
        5. General troubleshooting best practices
        
        Be thorough and methodical in your approach.
        """
    }
    
    return prompts.get(category, prompts["UNKNOWN"])

def handle_error_intelligently(error_msg: str, error_code: str, source: str = "unknown"):
    """Smart error handling with category-aware responses"""
    
    # Step 1: Categorize the error
    category, severity, auto_fixable = categorize_error(error_msg, error_code)
    
    # Step 2: Get tailored explanation from LLM
    try:
        explanation = qa.run(get_category_specific_prompt(category, error_msg))
    except Exception as e:
        explanation = f"Error analysis failed: {str(e)}"
    
    # Step 3: Send enhanced Slack message
    emoji_map = {
        "LOW": "🟡",
        "MEDIUM": "🟠", 
        "HIGH": "🔴"
    }
    
    send_slack_message(f"""
{emoji_map.get(severity, "⚠️")} *{category} Error* (Severity: {severity})
*Error Code:* `{error_code}`
*Source:* `{source}`
*Error Details:* `{error_msg}`
*Auto-fixable:* {'Yes' if auto_fixable else 'No'}

*Expert Analysis:*
{explanation}

💬 *Need more help?* <{CHATBOT_URL}|Open the Self-Healing Chatbot>
    """)
    
    return category, severity, auto_fixable


db_url = os.getenv("DATABASE_URL")
if db_url:
    # Normalize SQLAlchemy-style URL to psycopg2-compatible
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    conn = psycopg2.connect(db_url)
else:
    conn = psycopg2.connect(    # Fallback local development settings
        dbname="self_healing_app",
        user="siddhantamohanty",
        password="",
        host="localhost",
        port="5432"
    )
with conn.cursor() as cur:
    cur.execute("SET lock_timeout = '5s';")  # Set a lock timeout to avoid long waits on locks

embedder = OpenAIEmbeddings(
     model="text-embedding-3-small",
     api_key=os.environ["OPENAI_API_KEY"],
)

def load_or_create_vectorstore(embedder):
    if os.path.exists("faiss_index/index.faiss"):  #Checks if FAISS file exists
        return FAISS.load_local("faiss_index", embedder, allow_dangerous_deserialization=True)
    else:
        return FAISS.from_texts(["init"], embedder)

vectorstore = load_or_create_vectorstore(embedder)

llm = ChatOpenAI(
     model="gpt-3.5-turbo",
     temperature=0.2,
     api_key=os.environ["OPENAI_API_KEY"],
)

# Create RAG chain using LCEL (replaces deprecated RetrievalQA)
retriever = vectorstore.as_retriever()
template = """Answer the question based only on the following context. If you cannot answer the question using the context, say so.

Context: {context}

Question: {question}

Answer:"""
prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

qa = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# Create a wrapper to maintain compatibility with qa.run() calls
class QARunner:
    def __init__(self, chain):
        self.chain = chain
    
    def run(self, query):
        return self.chain.invoke(query)

qa = QARunner(qa)


@app.route('/')
def root():
    return render_template('index.html')

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    payload = request.get_json() or {}
    question = payload.get('question', '')
    include_recent = bool(payload.get('include_recent', True))

    if not question:
        return jsonify({"error": "question is required"}), 400

    # Get database context for intelligent responses
    db_context = ""
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Get employee count
            cur.execute("SELECT COUNT(*) as employee_count FROM employee;")
            emp_count = cur.fetchone()['employee_count']
            
            # Get recent employees
            cur.execute("SELECT name, email, department FROM employee ORDER BY id DESC LIMIT 5;")
            recent_emps = cur.fetchall()
            
            # Get error statistics
            cur.execute("SELECT COUNT(*) as error_count FROM error_logs;")
            error_count = cur.fetchone()['error_count']
            
            # Get recent errors
            cur.execute("""
                SELECT id, error_code, error_message, source, created_at
                FROM error_logs
                ORDER BY id DESC
                LIMIT 10;
            """)
            recent_errors = cur.fetchall()
            
            db_context = f"""Database Context:
- Total employees: {emp_count}
- Total errors logged: {error_count}
- Recent employees: {[dict(emp) for emp in recent_emps]}
- Recent errors: {[dict(err) for err in recent_errors]}
"""
    except Exception as e:
        db_context = f"Database context unavailable: {str(e)}"

    # Enhanced system prompt for better responses
    system_prompt = """You are a helpful database assistant for a self-healing system. You can:
1. Answer questions about database errors and their solutions
2. Provide statistics about employees and error logs
3. Explain database concepts and troubleshooting steps
4. Help with data analysis and insights

Always be helpful, accurate, and provide actionable advice. If you need specific data, mention that the user can ask for database queries."""

    composed_question = f"{system_prompt}\n\n{db_context}\n\nUser question: {question}"

    try:
        answer = qa.run(composed_question)
        return jsonify({"answer": answer}), 200
    except Exception as e:
        return jsonify({"error": f"chat failed: {e}"}), 500

@app.route('/employees', methods=['GET'])
def get_employees():    # view records of all employees
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur: # use DictCursor to get rows as dictionaries
            cur.execute("SELECT * FROM employee;")
            rows = cur.fetchall()
            return jsonify([dict(r) for r in rows]), 200   #successfully return the rows as a list of dictionaries
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {e}"}), 500  # Internal Server Error

@app.route('/add-employee', methods=['POST'])
def add_employee():  # add a new employee to the database
    data       = request.get_json() # get the JSON data from the request
    name       = data.get('name')
    email      = data.get('email') 
    department = data.get('department')

    try: # Check if all required fields are provided
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO employee (name, email, department) VALUES (%s, %s, %s);",
                (name, email, department)
            )
            conn.commit()
        return jsonify({"message": "Employee added ✅"}), 201   # Created successfully
    
    except psycopg2.IntegrityError as e:   # Handle duplicate email error
        conn.rollback()
        error_msg = str(e)

        with conn.cursor() as cur:    
            cur.execute(
                "INSERT INTO error_logs (error_code, error_message, source) VALUES (%s, %s, %s);",
                ("DUPLICATE_KEY", error_msg, "add_employee") # Log the error in the error_logs table
            )
            conn.commit()

        doc = Document(page_content=error_msg, metadata={"source": "add_employee"})  # Create a Document object with the error message and metadata
        vectorstore.add_documents([doc])   
        vectorstore.save_local("faiss_index")  

        # Use intelligent error handling
        category, severity, auto_fixable = handle_error_intelligently(error_msg, "DUPLICATE_KEY", "add_employee")

        return jsonify({"error": "Duplicate email. Logged in error_logs.", "category": category, "severity": severity}), 409   # Conflict

    except psycopg2.errors.LockNotAvailable as e:  # Handle table lock error
        conn.rollback()
        if e.pgcode == errorcodes.LOCK_NOT_AVAILABLE:  # Check if the error is due to a table lock
            error_msg = f"Table lock detected: {e}"
            error_code = "LOCK_NOT_AVAILABLE"
        else:
            error_msg = str(e)  # For any other psycopg2 error
            error_code = "UNEXPECTED_EXCEPTION"

        
        with conn.cursor() as cur:  # Log the error in the error_logs table
            cur.execute(
                "INSERT INTO error_logs (error_code, error_message, source) VALUES (%s, %s, %s);",
                (error_code, error_msg, "add_employee") 
            )
            conn.commit()

        doc = Document(page_content=error_msg, metadata={"source": "add_employee"})
        vectorstore.add_documents([doc])
        vectorstore.save_local("faiss_index")

        # Use intelligent error handling
        category, severity, auto_fixable = handle_error_intelligently(error_msg, error_code, "add_employee")

        return jsonify({"error": "Table is locked by another transaction.", "category": category, "severity": severity}), 503 # Service Unavailable

    except Exception as e:   # Handle any other unexpected exceptions
        conn.rollback()
        error_code = "UNEXPECTED_EXCEPTION"
        error_msg = str(e)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO error_logs (error_code, error_message, source)
                VALUES (%s, %s, %s);
                """, (error_code, error_msg, "add_employee"))
            conn.commit()

        doc = Document(page_content=error_msg, metadata={"source": "add_employee"})
        vectorstore.add_documents([doc])
        vectorstore.save_local("faiss_index")

        # Use intelligent error handling
        category, severity, auto_fixable = handle_error_intelligently(error_msg, error_code, "add_employee")
        
        return jsonify({"error": f"Unexpected error: {e}", "category": category, "severity": severity}), 500   # Internal Server Error

# API aliases used by the new frontend (keeps legacy routes too)
@app.route('/api/employees', methods=['GET'])
def api_get_employees():
    return get_employees()

@app.route('/api/employees', methods=['POST'])
def api_add_employee():
    return add_employee()

@app.route('/api/db-query', methods=['POST'])
def db_query():
    """Execute read-only database queries for chatbot intelligence"""
    payload = request.get_json() or {}
    query = payload.get('query', '').strip()
    
    if not query:
        return jsonify({"error": "query is required"}), 400
    
    # Security: Only allow SELECT queries
    if not query.upper().startswith('SELECT'):
        return jsonify({"error": "Only SELECT queries are allowed"}), 400
    
    # Additional security: Block dangerous keywords
    dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE']
    if any(keyword in query.upper() for keyword in dangerous_keywords):
        return jsonify({"error": "Query contains forbidden keywords"}), 400
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            # Convert to list of dicts for JSON serialization
            result = [dict(row) for row in rows]
            return jsonify({"result": result, "row_count": len(result)}), 200
    except Exception as e:
        return jsonify({"error": f"Query failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)  
