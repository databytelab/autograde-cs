"""Settings - your account, and (for the administrator) the people on it."""
from __future__ import annotations

import secrets

import streamlit as st

import sys
from pathlib import Path

# Streamlit puts only this file's directory on sys.path - see app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend_streamlit.components import api_client
from frontend_streamlit.components.ui import page_setup, require_auth

page_setup("Account")
user = require_auth()

st.title("Account")

st.markdown(f"**{user['name']}**")
st.caption(f"{user['email']} · {user['role']}"
           + ("  ·  administrator" if user.get("is_admin") else ""))

st.divider()

# ---------------------------------------------------------------------
# Change your own password
# ---------------------------------------------------------------------
st.subheader("Change your password")

with st.form("change_password"):
    current = st.text_input("Current password", type="password")
    new = st.text_input("New password", type="password",
                        help="At least 8 characters.")
    confirm = st.text_input("Repeat new password", type="password")
    submitted = st.form_submit_button("Change password", type="primary")

if submitted:
    if not current or not new:
        st.error("Fill in both your current and your new password.")
    elif new != confirm:
        st.error("The two new passwords do not match.")
    elif len(new) < 8:
        st.error("Your new password must be at least 8 characters.")
    elif api_client.change_password(current, new):
        st.success("Password changed. It applies the next time you sign in.")

# ---------------------------------------------------------------------
# Administrator: manage people
# ---------------------------------------------------------------------
if not user.get("is_admin"):
    st.stop()

st.divider()
st.subheader("People on this instance")
st.caption(
    "You are the administrator - the first account created on this "
    "installation. Self sign-up should stay switched off "
    "(`ALLOW_OPEN_REGISTRATION=false`) so that accounts are only created "
    "here."
)

people = api_client.list_users()
if people is not None:
    for person in people:
        label = f"{person['name']} — {person['email']}"
        if person.get("is_admin"):
            label += "  ·  administrator"
        if not person.get("is_active", True):
            label += "  ·  deactivated"

        with st.expander(label):
            st.caption(f"Role: {person['role']}")
            columns = st.columns([3, 2])

            with columns[0]:
                with st.form(f"reset_{person['id']}"):
                    st.markdown("**Reset their password**")
                    suggestion = st.text_input(
                        "New password", value=secrets.token_urlsafe(12),
                        help="Send this to them and ask them to change it "
                             "on this page after signing in.",
                    )
                    if st.form_submit_button("Reset password"):
                        if api_client.reset_user_password(person["id"], suggestion):
                            st.success("Done. Send them the new password.")

            with columns[1]:
                st.markdown("**Access**")
                if person["id"] == user["id"]:
                    st.caption("This is you.")
                elif not person.get("is_active", True):
                    st.caption("Already deactivated.")
                else:
                    st.caption("Blocks sign-in. Their courses and grades "
                               "are kept.")
                    if st.button("Deactivate", key=f"deact_{person['id']}"):
                        if api_client.deactivate_user(person["id"]):
                            st.success("Deactivated.")
                            st.rerun()

st.divider()
st.subheader("Add someone")

with st.form("create_user"):
    columns = st.columns([3, 3])
    new_name = columns[0].text_input("Full name", placeholder="Dr Colleague")
    new_email = columns[1].text_input("Email",
                                      placeholder="colleague@university.edu")
    columns = st.columns([3, 2])
    new_password = columns[0].text_input(
        "Initial password", value=secrets.token_urlsafe(12),
        help="Send this to them. They can change it on this page.",
    )
    new_role = columns[1].selectbox(
        "Role", ["professor", "ta"],
        help="TAs can grade and comment. Only professors can approve a "
             "grade or delete a course.",
    )
    if st.form_submit_button("Create account", type="primary"):
        if not new_name.strip() or not new_email.strip():
            st.error("A name and an email are both required.")
        elif len(new_password) < 8:
            st.error("The password must be at least 8 characters.")
        elif api_client.create_user(new_email.strip(), new_name.strip(),
                                    new_password, new_role):
            st.success(
                f"Created {new_email}. Send them the address of this site, "
                f"their email, and the password above."
            )
            st.rerun()
