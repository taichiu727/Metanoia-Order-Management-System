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
    with open("shopee_token.json", "w") as f:
        json.dump(token, f)

def load_token():
    try:
        if os.path.exists("shopee_token.json"):
            with open("shopee_token.json", "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None
    return None

def clear_token():
    if os.path.exists("shopee_token.json"):
        os.remove("shopee_token.json")