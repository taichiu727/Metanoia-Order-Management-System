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

def save_token(token):
    with db.conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO shopee_tokens (access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at
        """, (token["access_token"], token.get("refresh_token"), token.get("expires_at")))
        db.conn.commit()

def load_token():
    with db.conn.cursor() as cursor:
        cursor.execute("SELECT access_token FROM shopee_tokens ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            return {"access_token": result["access_token"]}
    return None

def clear_token():
    if os.path.exists("shopee_token.json"):
        os.remove("shopee_token.json")

# app.py
def main():
    st.title("Shopee Orders Tracker")
    
    # Initialize session states
    if "authentication_state" not in st.session_state:
        st.session_state.authentication_state = "initial"  # possible states: initial, pending, complete
    
    # Handle authentication flow
    if st.session_state.authentication_state != "complete":
        token = load_token()
        if token:
            st.session_state.authentication_state = "complete"
        else:
            auth_url = get_auth_url()
            st.markdown(f"[Authenticate with Shopee]({auth_url})")
        
        # Check for authentication code
        params = st.query_params
        if "code" in params:
            try:
                code = params["code"]
                # Clear the code from URL to prevent reuse
                st.session_state.authentication_state = "pending"
                
                token = fetch_token(code)
                save_token(token)
                st.session_state.authentication_state = "complete"
                # Clear query parameters
                st.query_params.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
                st.session_state.authentication_state = "initial"
                # Clear any existing token
                clear_token()
    else:
        token = load_token()
        if token and "access_token" in token:
            # Show last 4 characters of token for verification
            token_preview = f"...{token['access_token'][-4:]}"
            st.success(f"Authenticated! Token: {token_preview}")
            
            # Add logout button
            if st.button("Logout"):
                clear_token()
                st.session_state.authentication_state = "initial"
                st.rerun()
        else:
            st.error("Token not found or invalid")
            st.session_state.authentication_state = "initial"
            st.rerun()

if __name__ == "__main__":
    main()