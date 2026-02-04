from langchain_community.vectorstores import FAISS 
from dotenv import load_dotenv
load_dotenv()   
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

embedder = OpenAIEmbeddings(model="text-embedding-3-small")  
vectorstore = FAISS.load_local("faiss_index", embedder, allow_dangerous_deserialization=True)    #load_local tells langchain to load the index from the local directory

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.3)  

# Create RAG chain using LCEL (replaces deprecated RetrievalQA)
retriever = vectorstore.as_retriever()
template = """Answer the question based only on the following context. If you cannot answer the question using the context, say so.

Context: {context}

Question: {question}

Answer:"""
prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

qa_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

query = "duplicate key violates unique constraint"    #this is a placeholder query, it'll get changed based on the error you want to search for
answer = qa_chain.invoke(query)  #this will run the query 

print("Solution:", answer)
