import os   
import streamlit as st
import requests
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="Self-Healing Chatbot", page_icon="💬") 
st.title("💬 Self-Healing Assistant") #set the title 

if "messages" not in st.session_state: # Initialize session state to store messages
    st.session_state["messages"] = [] # this will store the chat history


for role, msg in st.session_state["messages"]: # Display previous messages in the chat
    with st.chat_message(role):
        st.markdown(msg)
        
if prompt := st.chat_input("Ask about your error …"):
    st.session_state["messages"].append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Call the backend (Flask /chat) or OpenAI directly
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            resp = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful debugging assistant."},
                    *[
                        {"role": r, "content": m}
                        for r, m in st.session_state["messages"]
                    ],
                    {"role": "user", "content": prompt},
                ],
            )
            reply = resp.choices[0].message.content.strip()

        except Exception as e:
            reply = f"❌ Error contacting assistant: {e}"

        st.markdown(reply)
        st.session_state["messages"].append(("assistant", reply))
