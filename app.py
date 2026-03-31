import streamlit as st
from vertexai import Client
import uuid
from dotenv import load_dotenv
import os
load_dotenv()


# --- Configuration ---
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
AGENT_ID = os.getenv("AGENT_ID")

st.set_page_config(page_title="My SRE Agent", page_icon="🤖")
st.title("My SRE Agent")

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
        {"role": "assistant", "content": "Hey I am Mira, your SRE Assistant. How can I help you?"}
    ]

# We ONLY use user_id. We have completely stripped out session_id.
if "user_id" not in st.session_state:
    st.session_state.user_id = f"streamlit_user_{uuid.uuid4().hex[:8]}"

# Render chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Stream Handler ---
def stream_agent_response(user_prompt, placeholder):
    full_response = ""
    
    # 🔥 THE FIX: Inject the entire chat history directly into the text prompt 🔥
    # Because the GCP database is broken, we manually give Mira her own memories.
    context_string = "You are Mira. Here is the conversation history so far:\n\n"
    for msg in st.session_state.messages:
        role_name = "User" if msg["role"] == "user" else "Mira"
        context_string += f"{role_name}: {msg['content']}\n"
    
    context_string += f"\nUser's newest message: {user_prompt}\n(Please respond to the newest message based on the history above.)"

    try:
        # We only pass message and user_id. No DB creation, no session crashes.
        for chunk in agent.stream_query(
            message=context_string,
            user_id=st.session_state.user_id
        ):
            if isinstance(chunk, dict):
                actions = chunk.get("actions", {})
                if "transfer_to_agent" in actions:
                    agent_name = actions["transfer_to_agent"]
                    full_response += f"\n\n*(Transferring you to the {agent_name}...)*\n\n"
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