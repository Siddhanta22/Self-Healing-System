from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import errorcodes
import psycopg2.extras
import requests
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.docstore.document import Document
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv   #Loads OpenAI API Key & Slack Webhook from .env
load_dotenv()   # populates os.environ["OPENAI_API_KEY"] from .env
from langchain_openai import OpenAIEmbeddings
import os

CHATBOT_URL = os.getenv("CHATBOT_URL", "http://localhost:8502")

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


conn = psycopg2.connect(    # Connect to PostgreSQL database
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
     openai_api_key=os.environ["OPENAI_API_KEY"],
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
     openai_api_key=os.environ["OPENAI_API_KEY"],
)

qa = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())   #pipeline to query the vector store and get answers from the LLM


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

        explanation = qa.run(error_msg) 

        send_slack_message(   #Format for which the error message will be sent to Slack
            f" *New Error:* `{error_msg}`\n"
            f" *Explanation & Fix:* {explanation}"
            f"➡️  *Need more help?* <{CHATBOT_URL}|Open the Self-Healing Chatbot>"
        )

        return jsonify({"error": "Duplicate email. Logged in error_logs."}), 409   # Conflict

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

        explanation = qa.run(error_msg)

        send_slack_message(
            f"*New Error:* `{error_msg}`\n"
            f"*Explanation & Fix:* {explanation}"
            f"➡️  *Need more help?* <{CHATBOT_URL}|Open the Self-Healing Chatbot>"        
        )

        return jsonify({"error": "Table is locked by another transaction."}), 503 # Service Unavailable

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

        explanation = qa.run(error_msg)
        send_slack_message(
            f"*New Error* **[{error_code}]** ```{error_msg}```\n"
            f"*Explanation & Fix:* {explanation}"
            f"➡️  *Need more help?* <{CHATBOT_URL}|Open the Self-Healing Chatbot>"
        )
        return jsonify({"error": f"Unexpected error: {e}"}), 500   # Internal Server Error

if __name__ == '__main__':
    app.run(debug=True)  
