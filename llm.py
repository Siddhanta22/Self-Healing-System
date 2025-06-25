from langchain_community.vectorstores import FAISS 
from dotenv import load_dotenv
load_dotenv()   
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA

embedder = OpenAIEmbeddings(model="text-embedding-3-small")  
vectorstore = FAISS.load_local("faiss_index", embedder)    #load_local tells langchain to load the index from the local directory

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.3)  

qa = RetrievalQA.from_chain_type(llm=llm, retriever=vectorstore.as_retriever())   #this will create a pipeline wherein the query will go
                                     #to the FAISS which will look for the error in the database and then the LLM will answer the query based on the retrieved documents

query = "duplicate key violates unique constraint"    #this is a placeholder query, it'll get changed based on the error you want to search for
answer = qa.run(query)  #this will run the query 

print("Solution:", answer)
