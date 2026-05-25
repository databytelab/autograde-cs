"""
Centralized API client for Streamlit — all requests go through here.
Automatically attaches JWT token from session state.
"""
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

def api_call(method: str, endpoint: str, **kwargs):
    """Make an authenticated API call."""
    headers = kwargs.pop("headers", {})
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is the FastAPI server running?")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e.response.status_code} — {e.response.text}")
        return None
