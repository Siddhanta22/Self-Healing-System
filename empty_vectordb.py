import os 
import psycopg2   # import psycopg2 to connect to PostgreSQL
from dotenv import load_dotenv   #load api keys from .env file
load_dotenv()   
from langchain_openai import OpenAIEmbeddings   
from langchain_community.vectorstores import FAISS   # import FAISS vector store to store the error logs in a vector database

# Load API keys from .env
load_dotenv()
openai_key = os.environ["OPENAI_API_KEY"]

# Connect to PostgreSQL i.e. establish a connection to the error logs database
conn = psycopg2.connect(
    dbname="self_healing_app",
    user="siddhantamohanty",  
    password="",             
    host="localhost",     
    port="5432"
)

def fetch_error_logs():  # Fetch error logs from the database
    with conn.cursor() as cur:
        cur.execute("SELECT id, error_message FROM error_logs;")
        rows = cur.fetchall()
    return [{"id": r[0], "message": r[1]} for r in rows]   #format the rows into a list of dictionaries


def store_in_vector_db(error_logs):
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")  # Initialize the OpenAI embeddings model

    texts = [e["message"] for e in error_logs]   # divide the error logs into chunks of text

    metadatas = [{"id": e["id"]} for e in error_logs]   # create metadata for each error log with its ID

    vectorstore = FAISS.from_texts(texts, embedder, metadatas=metadatas)   #to store the error logs in a FAISS vector store
    vectorstore.save_local("faiss_index") # saves the error db on local disk 
    print("✅ Stored errors in local FAISS DB.") 

    
