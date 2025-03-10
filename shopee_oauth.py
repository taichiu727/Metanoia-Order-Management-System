# shopee_oauth.py
import os
import json
import time
import hmac
import hashlib
import requests
import streamlit as st
import datetime
from datetime import timedelta

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

def get_products(access_token):
    """Fetch all products from Shopee API33"""
    now = int(time.time())
    thirty_days_ago = now - (30 * 24 * 60 * 60)
    
    path = "/api/v2/product/get_item_list"
    params = {
        'access_token': access_token,
        'item_status': 'NORMAL',
        'offset': 0,
        'page_size': 100,
        'partner_id': CLIENT_ID,
        'shop_id': SHOP_ID,
        'timestamp': now,
        'update_time_from': thirty_days_ago,
        'update_time_to': now
    }

    base_string = f"{CLIENT_ID}{path}{now}{access_token}{SHOP_ID}"
    sign = hmac.new(
        CLIENT_SECRET.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    params['sign'] = sign
    url = f"https://partner.shopeemobile.com{path}"
    
    all_products = []
    has_more = True
    
    while has_more:
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if "response" in data:
                    products = data["response"].get("item", [])
                    all_products.extend(products)
                    has_more = data["response"].get("has_next_page", False)
                    if has_more:
                        params['offset'] = data["response"].get("next_offset", params['offset'] + params['page_size'])
                else:
                    break
            else:
                raise Exception(f"Error fetching products: {response.text}")
            time.sleep(0.5)
        except Exception as e:
            raise Exception(f"Error: {str(e)}")
            
    return all_products

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
                
            # Add the fetch_time AFTER we have the data object
            data["fetch_time"] = int(time.time())
            
            # Default to ~1 year if not provided by the API
            if "refresh_token_expire_in" not in data:
                data["refresh_token_expire_in"] = 365 * 24 * 60 * 60
                
            return data
        else:
            raise Exception(f"API Error: Status {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")

def refresh_token(refresh_token):
    """Refresh the access token using refresh token"""
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
            data = response.json()
            if "error" in data and data["error"]:
                raise ValueError(f"API Error: {data.get('message', 'No error message provided')}")
            if "access_token" not in data:
                raise ValueError("Access token missing in response")
            # Add fetch time to token data
            data["fetch_time"] = int(time.time())
            return data
        else:
            raise Exception(f"API Error: Status {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")

def is_token_valid(token_data):
    """Check if the token is still valid and not near expiration"""
    if not token_data or "access_token" not in token_data:
        return False
        
    current_time = int(time.time())
    fetch_time = token_data.get("fetch_time", 0)
    expire_in = token_data.get("expire_in", 0)
    
    # Add more logging to understand token status
    time_left = fetch_time + expire_in - current_time
    print(f"Token expires in: {time_left} seconds")
    
    # If access token is expired, don't consider it valid regardless of refresh token
    if time_left <= 0:
        return False
        
    # For soon-to-expire tokens, still validate but prepare for refresh
    if time_left <= 300:
        return "refresh_token" in token_data
        
    return True

def get_valid_token(db, force_refresh=False):
    """Get a valid token from database, refresh if needed"""
    token_data = db.load_token()
    
    if not token_data:
        return None
    
    current_time = int(time.time())
    fetch_time = token_data.get("fetch_time", 0)
    expire_in = token_data.get("expire_in", 0)
    time_left = fetch_time + expire_in - current_time
    
    # Force refresh or refresh if expiring soon
    if force_refresh or time_left <= 300:
        if "refresh_token" in token_data:
            try:
                print("Refreshing token...")
                new_token_data = refresh_token(token_data["refresh_token"])
                if new_token_data and "access_token" in new_token_data:
                    db.save_token(new_token_data)
                    return new_token_data
            except Exception as e:
                print(f"Error refreshing token: {str(e)}")
                # If we forced refresh and it failed, return None
                if force_refresh:
                    return None
    
    # Return existing token if still valid            
    return token_data if is_token_valid(token_data) else None