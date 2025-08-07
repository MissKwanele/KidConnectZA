# ------------------------------------------------------------------------

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright © 2025 Miss Kwanele Ntshele

import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests.auth import HTTPBasicAuth
import chardet
from PIL import Image
import json
import base64

# --- App Branding ---
st.set_page_config(page_title="KidConnect", page_icon="📱", layout="wide")

# Load and display logo in sidebar
logo_path = "KidKonnectZA Logo.png"
try:
    logo = Image.open(logo_path)
    st.sidebar.image(logo, width=150)
except FileNotFoundError:
    st.sidebar.error(f"Logo file not found at {logo_path}")

# Sidebar title and description
st.sidebar.title("📚 KidConnectZA")
st.sidebar.markdown("""
Welcome to **KidConnectZA**!
Send termly updates, class announcements, and school-wide WhatsApp messages.
""")

# --- Welcome screen / header ---
st.markdown("<h1 style='text-align: center;'>Welcome to KidConnectZA 📲</h1>", unsafe_allow_html=True)
st.markdown("""
<p style='text-align: center; font-size:18px;'>
An easy-to-use messaging tool for teachers and principals to connect with parents.
</p>
""", unsafe_allow_html=True)

# --------------------
# Config from secrets.toml
# --------------------
try:
    VONAGE_API_KEY = st.secrets["vonage"]["api_key"]
    VONAGE_API_SECRET = st.secrets["vonage"]["api_secret"]
    VONAGE_FROM_NUMBER = st.secrets["vonage"]["from_number"]
    WHITELIST = st.secrets["vonage"]["whitelist"]

    SPREADSHEET_ID = st.secrets["google"]["spreadsheet_url"]
    
    # --- This part is changed to decode the Base64 string ---
    GOOGLE_SA_INFO_ENCODED = st.secrets["google_service_account"]["base64_encoded_json"]
    GOOGLE_SA_INFO_DECODED = base64.b64decode(GOOGLE_SA_INFO_ENCODED).decode('utf-8')
    GOOGLE_SA_INFO = json.loads(GOOGLE_SA_INFO_DECODED)
except KeyError as e:
    st.error(f"Missing a required secret. Please check your secrets configuration: {e}")
    st.stop()

# --------------------
# Connect to Google Sheets
# --------------------
@st.cache_resource(ttl=300)  # Cache for 1 hour or adjust based on needs
def get_google_sheet():
    try:
        # Decode base64 JSON from secrets
        GOOGLE_SA_INFO = json.loads(base64.b64decode(st.secrets["google_service_account"]["base64_encoded_json"]).decode("utf-8"))
        SPREADSHEET_ID = st.secrets["google"]["spreadsheet_url"]
        
        # Setup credentials and authorize with Google Sheets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_SA_INFO, scope)
        client = gspread.authorize(creds)

        # Open the spreadsheet and worksheets
        sheet_main = client.open_by_key(SPREADSHEET_ID)
        parent_sheet = sheet_main.worksheet("Parents")
        termly_sheet = sheet_main.worksheet("TermlyActivities")
        
        # Create MessageLog worksheet if not found
        try:
            message_log_sheet = sheet_main.worksheet("MessageLog")
        except gspread.WorksheetNotFound:
            st.warning("MessageLog worksheet not found. Creating a new one...")
            message_log_sheet = sheet_main.add_worksheet(title="MessageLog", rows="100", cols="20")
            message_log_sheet.append_row(["Timestamp", "Recipient Name", "Recipient Number", "Class", "Message Content"])

        return parent_sheet, termly_sheet, message_log_sheet
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets. Check your secrets and sheet permissions: {e}")
        st.stop()

# Initialize Google Sheets
try:
    parent_sheet, termly_sheet, message_log_sheet = get_google_sheet()
except Exception as e:
    st.error(f"Failed to initialize Google Sheets connection: {e}")
    st.stop()


# --------------------
# Authentication
# --------------------
def authenticate(user, password):
    users = {
        "principal": "admin123", # WARNING: Use a secure method for passwords in a real app!
        "staff": "staff123"      # Example: Use st.secrets to store a hashed password
    }
    return users.get(user) == password

# --------------------
# Send WhatsApp Message via Vonage
# --------------------
def send_whatsapp_message(to_number, message):
    url = "https://messages-sandbox.nexmo.com/v1/messages"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "from": VONAGE_FROM_NUMBER,
        "to": to_number,
        "message_type": "text",
        "text": message,
        "channel": "whatsapp"
    }
    try:
        response = requests.post(url, headers=headers, json=payload,
                                 auth=HTTPBasicAuth(VONAGE_API_KEY, VONAGE_API_SECRET))
        return response.status_code, response.text
    except Exception as e:
        return 500, f"Request failed: {e}"

# --------------------
# Streamlit UI
# --------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.logged_in:
    st.subheader("🔐 Login")

    with st.form("login_form"):
        username = st.text_input("Username (principal/staff)")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")

    if submit_button:
        if authenticate(username, password):
            st.session_state.logged_in = True
            st.session_state.user = username
            st.success("Logged in!")
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()

# Dashboard after login
st.success(f"Logged in as {st.session_state.user.capitalize()}")

# --- Idle Timeout Script ---
if st.session_state.logged_in:
    timeout_in_minutes = 5
    warning_in_seconds = 30
    
    idle_js = f"""
    <script>
    var timeout = {timeout_in_minutes * 60 * 1000};
    var warningTime = {timeout_in_minutes * 60 * 1000 - warning_in_seconds * 1000};
    var timer;

    function resetTimer() {{
        clearTimeout(timer);
        timer = setTimeout(showWarning, warningTime);
    }}

    function showWarning() {{
        // We can't directly show a Streamlit warning here,
        // so we'll just log to the console. The next step
        // will trigger the logout.
        console.log("Session will time out soon due to inactivity.");
        timer = setTimeout(logout, {warning_in_seconds} * 1000);
    }}

    function logout() {{
        // This is a special Streamlit function to signal a rerun.
        // We'll use a unique key in the URL to trigger the logout.
        window.location.href = window.location.href.split('?')[0] + '?logout=true';
    }}

    document.addEventListener('mousemove', resetTimer);
    document.addEventListener('keypress', resetTimer);
    document.addEventListener('click', resetTimer);

    resetTimer();
    </script>
    """
    
    st.components.v1.html(idle_js, height=0)

    # Check for the logout signal in the URL
    query_params = st.query_params
    if 'logout' in query_params and query_params['logout'] == 'true':
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

    # The rest of your app code (tabs, etc.) goes here
    # ----------------------------------------------------

if st.session_state.user == "principal":
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Send Message", "Message Log", "Upload Parent List", "📅 Termly Activities", "⏰ Daily Scheduler"])
else:
    tab1, tab2, tab3 = st.tabs(["Send Message", "Message Log", "Upload Parent List"])

with tab1:
    st.subheader("✉️ Compose Message")
    class_selected = st.radio("Select Class", ["All Classes"])
    message_text = st.text_area("Message to Parents")
    send_now = st.button("Send Now")

    if send_now and message_text:
        try:
            data = parent_sheet.get_all_records()
            sent_count = 0
            for row in data:
                if class_selected != "All Classes" and row.get("Class") != class_selected:
                    continue
                name = row.get("Parent", "")
                number = str(row.get("PhoneNumber", "")).strip()

                # Check for number format and whitelist
                if not number or number not in WHITELIST:
                    st.warning(f"Skipping {name} ({number}): no phone number or not in whitelist")
                    continue

                full_msg = f"Hi {name}, {message_text}"
                status, resp = send_whatsapp_message(number, full_msg)

                if status == 202:
                    st.success(f"Sent to {name} ({number})")
                    sent_count += 1
                    # Log to the correct message log sheet
                    log_row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, number, row.get("Class", "Unknown"), message_text]
                    message_log_sheet.append_row(log_row)
                    time.sleep(1) # Add a small delay to avoid rate limits
                else:
                    st.error(f"Failed to send to {name} ({number}): {resp}")
            st.info(f"Total messages sent: {sent_count}")
        except Exception as e:
            st.error(f"An error occurred while sending messages: {e}")

with tab2:
    st.subheader("📊 Message Log")
    try:
        df_log = pd.DataFrame(message_log_sheet.get_all_records())
        st.dataframe(df_log)
    except Exception:
        st.error("Could not load message log. Check sheet permissions.")

with tab3:
    st.subheader("📁 Upload Parent List (.csv)")
    uploaded_file = st.file_uploader("Upload CSV file", type=["csv"])
    if uploaded_file:
        try:
            raw_data = uploaded_file.read()
            detected = chardet.detect(raw_data)
            encoding = detected['encoding']
            uploaded_file.seek(0)
            df_parents = pd.read_csv(uploaded_file, encoding=encoding)

            parent_sheet.clear()
            parent_sheet.append_row(df_parents.columns.tolist())
            for _, row in df_parents.iterrows():
                parent_sheet.append_row(row.tolist())
            st.success("Parent list uploaded and saved to Google Sheet!")
        except Exception as e:
            st.error(f"Failed to upload parent list: {e}")

if st.session_state.user == "principal":
    with tab4:
        st.subheader("📅 Upload Termly Activities (.csv)")
        uploaded_activities = st.file_uploader("Upload Termly Activities CSV", type=["csv"], key="activities")
        if uploaded_activities:
            try:
                raw_data = uploaded_activities.read()
                detected = chardet.detect(raw_data)
                encoding = detected['encoding']
                uploaded_activities.seek(0)
                df_activities = pd.read_csv(uploaded_activities, encoding=encoding)

                termly_sheet.clear()
                termly_sheet.append_row(df_activities.columns.tolist())
                for _, row in df_activities.iterrows():
                    termly_sheet.append_row(row.tolist())
                st.success("Termly activities uploaded!")
            except Exception as e:
                st.error(f"Failed to upload termly activities: {e}")

        st.markdown("---")
        st.subheader("📖 View Uploaded Termly Activities")
        try:
            df_activities_view = pd.DataFrame(termly_sheet.get_all_records())
            st.dataframe(df_activities_view)
        except Exception:
            st.error("Could not load termly activities.")

    with tab5:
        st.subheader("📅 Send Today's Scheduled Messages")
        st.markdown("This will send all messages scheduled for today from the TermlyActivities sheet to all parents.")

        send_daily_messages_button = st.button("Send Today's Messages")

        if send_daily_messages_button:
            try:
                today_date_str = datetime.now().strftime("%Y-%m-%d")
                st.info(f"Checking for messages scheduled on {today_date_str}...")

                activities_data = termly_sheet.get_all_records()
                messages_to_send = [row for row in activities_data if str(row.get("Date")) == today_date_str]

                if not messages_to_send:
                    st.warning("No messages are scheduled for today.")
                else:
                    st.success(f"Found {len(messages_to_send)} message(s) to send.")

                    parent_data = parent_sheet.get_all_records()
                    sent_count = 0

                    for parent_row in parent_data:
                        name = parent_row.get("name", "")
                        number = str(parent_row.get("PhoneNumber", "")).strip()

                        if not number or number not in WHITELIST:
                            st.warning(f"Skipping {name} ({number}): no phone number or not in whitelist.")
                            continue

                        # Combine all messages for the day into one
                        full_message_body = ""
                        for message_row in messages_to_send:
                            message_text = message_row.get("Message", "A daily update.")
                            full_message_body += f"{message_text}\n\n"

                        closing_message = "Thank you, have a lovely day - Speelkas Admin"
                        final_message = f"Hello {name},\n\n{full_message_body.strip()}\n{closing_message}"

                        status, resp = send_whatsapp_message(number, final_message)
                        if status == 202:
                            st.success(f"Sent scheduled message to {name} ({number})")
                            sent_count += 1
                            log_row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, number, parent_row.get("Class"), "Scheduled: " + full_message_body]
                            message_log_sheet.append_row(log_row)
                        else:
                            st.error(f"Failed to send scheduled message to {name} ({number}): {resp}")
                    st.info(f"Total scheduled messages sent: {sent_count}")
            except Exception as e:
                st.error(f"An error occurred while sending scheduled messages: {e}")

st.markdown("---")
st.caption("Built with ❤️ using Streamlit by a Fellow Mommy | Vonage Sandbox Demo")
