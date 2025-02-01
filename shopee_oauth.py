# shopee_oauth.py
import os
import json
import time
import hmac
import hashlib
import requests
import streamlit as st

# Configuration
CLIENT_ID = "2007044"
CLIENT_SECRET = "5a7a4d6469566c446b645866566478674c6f594f4d4a6d46494b5a6b714e4457"
SHOP_ID = 26174521
REDIRECT_URI = "https://metanoia-order.streamlit.app/"

def is_admin():
    """Check if the current user is an admin"""
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
    """Generate API signature for Shopee authentication"""
    base_string = f"{partner_id}{path}{timestamp}".encode()
    return hmac.new(
        partner_key.encode(),
        base_string,
        hashlib.sha256
    ).hexdigest()

def get_auth_url():
    """Generate Shopee authentication URL"""
    timestamp = int(time.time())
    path = "/api/v2/shop/auth_partner"
    signature = generate_signature(CLIENT_ID, CLIENT_SECRET, path, timestamp)
    return (f"https://partner.shopeemobile.com/api/v2/shop/auth_partner?"
            f"partner_id={CLIENT_ID}&timestamp={timestamp}&sign={signature}&"
            f"redirect={REDIRECT_URI}")

def save_token(token):
    """Save token to session state with expiration tracking"""
    token['stored_at'] = time.time()
    st.session_state['admin_token'] = token

def load_token():
    """Load token from session state with expiration check"""
    token = st.session_state.get('admin_token')
    if token:
        # Check if token is expired (4 hours validity)
        stored_time = token.get('stored_at', 0)
        if time.time() - stored_time > 14400:  # 4 hours in seconds
            return None
        return token
    return None

def fetch_token(code):
    """Fetch access token from Shopee API"""
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
            # Only raise error if both error field exists and is non-empty
            if "error" in data and data["error"]:
                raise ValueError(f"API Error: {data.get('message', 'No error message provided')}")
            if "access_token" not in data:
                raise ValueError("Access token missing in response")
            return data
        else:
            raise Exception(f"API Error: Status {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")

def clear_token():
    """Clear the admin token from session state"""
    st.session_state.pop('admin_token', None)
    st.session_state.authentication_state = "initial"
    st.session_state.is_admin = False

def refresh_token(refresh_token):
    """Refresh the access token"""
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