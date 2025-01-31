import os
import json
import time
import hmac
import hashlib
import requests
import streamlit as st
from datetime import datetime, timedelta

# Configuration
CLIENT_ID = "2007044"
CLIENT_SECRET = "5a7a4d6469566c446b645866566478674c6f594f4d4a6d46494b5a6b714e4457"
SHOP_ID = 26174521
REDIRECT_URI = "https://metanoia-order.streamlit.app/"

# Use Streamlit secrets for token storage
def save_token(token):
    # Add expiration timestamp
    token['stored_at'] = time.time()
    st.session_state['admin_token'] = token

def load_token():
    token = st.session_state.get('admin_token')
    if token:
        # Check if token is expired (assuming 4 hour validity)
        stored_time = token.get('stored_at', 0)
        if time.time() - stored_time > 14400:  # 4 hours in seconds
            return None
        return token
    return None

def is_admin():
    # You can set this password in Streamlit Cloud's secrets
    admin_password = st.secrets.get("ADMIN_PASSWORD", "your_default_password")
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    
    if not st.session_state.is_admin:
        password = st.sidebar.text_input("Admin Password", type="password")
        if password == admin_password:
            st.session_state.is_admin = True
            return True
        return False
    return True

def generate_signature(partner_id, partner_key, path, timestamp):
    base_string = f"{partner_id}{path}{timestamp}".encode()
    return hmac.new(
        partner_key.encode(),
        base_string,
        hashlib.sha256
    ).hexdigest()

def get_auth_url():
    timestamp = int(time.time())
    path = "/api/v2/shop/auth_partner"
    signature = generate_signature(CLIENT_ID, CLIENT_SECRET, path, timestamp)
    return (f"https://partner.shopeemobile.com/api/v2/shop/auth_partner?"
            f"partner_id={CLIENT_ID}&timestamp={timestamp}&sign={signature}&"
            f"redirect={REDIRECT_URI}")

def fetch_token(code):
    if not code:
        raise ValueError("Authorization code is required")
        
    timestamp = int(time.time())
    path = "/api/v2/auth/token/get"
    signature = generate_signature(CLIENT_ID, CLIENT_SECRET, path, timestamp)
    
    url = f"https://partner.shopeemobile.com{path}"
    params = {
        "partner_id": CLIENT_ID,
        "timestamp": timestamp,
        "sign": signature
    }
    
    payload = {
        "code": code,
        "shop_id": SHOP_ID,
        "partner_id": int(CLIENT_ID)
    }
    
    try:
        response = requests.post(url, params=params, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "error" in data and data["error"]:
                raise ValueError(f"API Error: {data.get('message', 'No error message provided')}")
            if "access_token" not in data:
                raise ValueError("Access token missing in response")
            return data
        else:
            raise Exception(f"API Error: Status {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")

def refresh_token(refresh_token):
    timestamp = int(time.time())
    path = "/api/v2/auth/access_token/get"
    signature = generate_signature(CLIENT_ID, CLIENT_SECRET, path, timestamp)
    
    url = f"https://partner.shopeemobile.com{path}"
    params = {
        "partner_id": CLIENT_ID,
        "timestamp": timestamp,
        "sign": signature
    }
    
    payload = {
        "refresh_token": refresh_token,
        "shop_id": SHOP_ID,
        "partner_id": int(CLIENT_ID)
    }
    
    try:
        response = requests.post(url, params=params, json=payload)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Token refresh failed: {response.text}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Token refresh failed: {str(e)}")

def main():
    st.title("Shopee Orders Tracker")
    
    # Initialize session states
    if "authentication_state" not in st.session_state:
        st.session_state.authentication_state = "initial"
    
    # Show different views for admin and regular users
    if is_admin():
        # Admin view - can authenticate and manage token
        if st.session_state.authentication_state != "complete":
            auth_url = get_auth_url()
            st.markdown(f"[Authenticate with Shopee]({auth_url})")
            
            params = st.query_params
            if "code" in params:
                try:
                    code = params["code"]
                    st.session_state.authentication_state = "pending"
                    
                    token = fetch_token(code)
                    save_token(token)
                    st.session_state.authentication_state = "complete"
                    st.query_params.clear()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
                    st.session_state.authentication_state = "initial"
        else:
            token = load_token()
            if token and "access_token" in token:
                token_preview = f"...{token['access_token'][-4:]}"
                st.success(f"Authenticated as admin! Token: {token_preview}")
                
                if st.button("Logout"):
                    st.session_state.pop('admin_token', None)
                    st.session_state.authentication_state = "initial"
                    st.session_state.is_admin = False
                    st.rerun()
    else:
        # Regular user view - just uses the stored token
        token = load_token()
        if token and "access_token" in token:
            st.success("Connected to Shopee API")
            # Add your order management functionality here
        else:
            st.warning("System is not configured. Please contact administrator.")

if __name__ == "__main__":
    main()