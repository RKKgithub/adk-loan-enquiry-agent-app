import streamlit as st
from vertexai import Client
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
AGENT_ID = os.getenv("AGENT_ID")

st.set_page_config(page_title="Mira - Loan Enquiry", page_icon="🏦")
st.title("Mira - Loan Enquiry Assistant")

# --- Sidebar: Document Upload ---
with st.sidebar:
    st.header("📄 Document Upload")
    st.write("Upload your salary slip here when requested by Mira.")
    uploaded_file = st.file_uploader("Upload Salary Slip (.txt or .pdf)", type=["txt", "pdf"])
    
    if uploaded_file is not None:
        # Read the file content into session state
        try:
            file_content = uploaded_file.read().decode("utf-8", errors="ignore")
            st.session_state.uploaded_file_content = file_content
            st.session_state.uploaded_file_name = uploaded_file.name
            st.success(f"Successfully uploaded: {uploaded_file.name}")
        except Exception as e:
            st.error(f"Error reading file: {e}")
    else:
        # Clear it if the user removes the file
        st.session_state.pop("uploaded_file_content", None)
        st.session_state.pop("uploaded_file_name", None)

# --- Initialize Vertex AI Agent ---
@st.cache_resource
def load_agent():
    client = Client(project=PROJECT_ID, location=LOCATION)
    agent_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ID}"
    agent = client.agent_engines.get(name=agent_name)
    return agent

try:
    agent = load_agent()
except Exception as e:
    st.error(f"Failed to load agent. Error: {e}")
    st.stop()

# --- Initialize Chat History & User ID ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! I am Mira, your Loan Enquiry Assistant. I can help you check your loan eligibility in just a few minutes. To get started, what type of loan are you looking for, and how much do you need?"}
    ]

# We ONLY use user_id to maintain state consistency
if "user_id" not in st.session_state:
    st.session_state.user_id = f"streamlit_user_{uuid.uuid4().hex[:8]}"

# Render chat history natively
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Stream Handler ---
def stream_agent_response(user_prompt, placeholder):
    full_response = ""
    
    # 🔥 Inject the chat history directly into the text prompt 🔥
    context_string = "You are Mira, a Loan Enquiry Assistant. Here is the conversation history so far:\n\n"
    for msg in st.session_state.messages:
        role_name = "User" if msg["role"] == "user" else "Mira"
        context_string += f"{role_name}: {msg['content']}\n"
    
    # 🔥 Inject uploaded document text into the context if available in the sidebar 🔥
    if "uploaded_file_content" in st.session_state:
        context_string += f"\n[SYSTEM NOTE: The user has uploaded a document named '{st.session_state.uploaded_file_name}' via the sidebar. "
        context_string += f"Document Content:\n{st.session_state.uploaded_file_content}]\n"

    context_string += f"\nUser's newest message: {user_prompt}\n(Please respond to the newest message based on the history and any system notes above.)"

    try:
        # Stream the query
        for chunk in agent.stream_query(
            message=context_string,
            user_id=st.session_state.user_id
        ):
            if isinstance(chunk, dict):
                actions = chunk.get("actions", {})
                if "transfer_to_agent" in actions:
                    agent_name = actions["transfer_to_agent"]
                    # Format agent name to look nicer (e.g., intake_agent -> Intake Agent)
                    pretty_name = agent_name.replace("_", " ").title()
                    full_response += f"\n\n*(Transferring you to the {pretty_name}...)*\n\n"
                    placeholder.markdown(full_response + "▌")

                parts = chunk.get("content", {}).get("parts", [])
                for part in parts:
                    if "text" in part:
                        if full_response and not full_response.endswith("\n"):
                            full_response += " "
                        full_response += part["text"]
                        placeholder.markdown(full_response + "▌")

    except Exception as e:
        import traceback
        error_msg = f"❌ Error: {str(e)}\n\n{traceback.format_exc()}"
        placeholder.error(error_msg)
        return error_msg

    placeholder.markdown(full_response)
    return full_response

# --- Chat Input ---
if prompt := st.chat_input("Type a message..."):
    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        final_response = stream_agent_response(prompt, response_placeholder)
        
        if final_response and not final_response.startswith("❌"):
            # Add Mira's response to UI
            st.session_state.messages.append({"role": "assistant", "content": final_response})