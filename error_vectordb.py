from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
load_dotenv()   
from langchain_openai import OpenAIEmbeddings  
import os # import os to check if the vector store i.e. FAISS exists

def add_error_to_vector_db(error_message, error_id):    #turns the error into vectors for the LLM to process
    try:
        embedder = OpenAIEmbeddings(model="text-embedding-3-small")  # use OpenAI to turn error msgs/strings into embeddings

        error_doc = Document (page_content = error_message, metadata= {"error_id": error_id})  #format the error message into a Document object with metadata 
                                 #where metadate links it to the original error log ID        

        if os.path.exists("faiss_index"):   #check if the FAISS index already exists
            vectorstore = FAISS.load_local("faiss_index", embedder)
            vectorstore.add_documents([error_doc])  # if yes then Add the error document to the existing vector store
        else:
            vectorstore = FAISS.from_documents([error_doc], embedder)  # or else Create a new vector store with the error document

        vectorstore.save_local("faiss_index")    #this writes the updated state (with my new error) to disk
        print("✅ Error embedded and stored in FAISS.")
    
    except Exception as e:
        print(f" Failed to embed/store error: {e}") 