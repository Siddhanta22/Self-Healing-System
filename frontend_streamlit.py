import streamlit as st
import pandas as pd
import requests

# Point these at your running Flask service
BASE_URL = "http://127.0.0.1:5000"

st.set_page_config(page_title="Self-Healing App UI")

st.title("🔧 Self-Healing Database App")


page = st.sidebar.selectbox("Choose an action", ["View Records", "Add Record"])


if page == "View Records":
    st.header("📋 Employee Records")
    try:
        resp = requests.get(f"{BASE_URL}/employees")
        resp.raise_for_status()
        df = pd.DataFrame(resp.json())
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to load records: {e}")


else:
    st.header("➕ Add a New Employee")

    with st.form("add_employee_form", clear_on_submit=True):
        name       = st.text_input("Name")
        email      = st.text_input("Email")
        department = st.text_input("Department")
        submitted  = st.form_submit_button("Submit")

    if submitted:
        if not (name and email and department):
            st.warning("Please fill out all fields.")
        else:
            payload = {"name": name, "email": email, "department": department}
            try:
                post = requests.post(f"{BASE_URL}/add-employee", json=payload)
                if post.status_code == 201:
                    st.success("✅ Employee added!")
                else:
                    err = post.json().get("error", post.text)
                    st.error(f"⚠️ {err}")
            except Exception as e:
                st.error(f"Request failed: {e}")
