import streamlit as st
import hmac
import pandas as pd
from shopee_oauth import (
    get_auth_url, 
    fetch_token, 
    save_token, 
    load_token,
    CLIENT_ID,
    CLIENT_SECRET,
    SHOP_ID,
    clear_token
)
import requests
import hashlib
import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

# Database Configuration
DATABASE_URL = "postgresql://neondb_owner:npg_r9iSFwQd4zAT@ep-white-sky-a1mrgmyd-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

class OrderDatabase:
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def connect(self):
        try:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        except Exception as e:
            st.error(f"Database connection failed: {str(e)}")
            raise e

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def init_tables(self):
        try:
            self.connect()
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_tracking (
                    order_sn VARCHAR(50),
                    product_name TEXT,
                    received BOOLEAN DEFAULT FALSE,
                    missing_count INTEGER DEFAULT 0,
                    note TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (order_sn, product_name)
                )
            """)
            self.conn.commit()
        finally:
            self.close()

    def upsert_order_tracking(self, order_sn, product_name, received, missing_count, note):
        try:
            self.connect()
            self.cursor.execute("""
                INSERT INTO order_tracking (order_sn, product_name, received, missing_count, note, last_updated)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (order_sn, product_name) 
                DO UPDATE SET 
                    received = EXCLUDED.received,
                    missing_count = EXCLUDED.missing_count,
                    note = EXCLUDED.note,
                    last_updated = CURRENT_TIMESTAMP
            """, (order_sn, product_name, received, missing_count, note))
            self.conn.commit()
        finally:
            self.close()

    def get_order_tracking(self):
        try:
            self.connect()
            self.cursor.execute("""
                SELECT order_sn, product_name, received, missing_count, note
                FROM order_tracking
            """)
            return self.cursor.fetchall()
        finally:
            self.close()

# Callback to update checkbox state
def update_checkbox_state(checkbox_key):
    st.session_state.checkbox_states[checkbox_key] = not st.session_state.checkbox_states.get(checkbox_key, False)

def generate_api_signature(api_type, partner_id, path, timestamp, access_token, shop_id, client_secret):
    """
    Generate Shopee API signature according to official documentation
    """
    partner_id = str(partner_id)
    timestamp = str(timestamp)
    shop_id = str(shop_id) if shop_id else ""

    components = [partner_id, path, timestamp]
    
    if api_type == 'shop':
        components += [access_token, shop_id]
    elif api_type == 'merchant':
        components += [access_token, str(merchant_id)]
    elif api_type == 'public':
        pass
    else:
        raise ValueError("Invalid API type. Use 'shop', 'merchant', or 'public'")

    base_string = ''.join(components)
    
    return hmac.new(
        client_secret.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().lower()

def get_orders(access_token, client_id, client_secret, shop_id):
    all_orders = []
    max_retries = 3
    retry_delay = 1
    
    end_time = int(time.time())
    total_days = 30
    window_size = 15
    
    time_windows = []
    current_end = end_time
    days_remaining = total_days
    
    while days_remaining > 0:
        window_days = min(window_size, days_remaining)
        current_start = int((datetime.fromtimestamp(current_end) - timedelta(days=window_days)).timestamp())
        time_windows.append((current_start, current_end))
        current_end = current_start
        days_remaining -= window_days
    
    for time_from, time_to in time_windows:
        cursor = None
        has_more = True
        
        while has_more:
            for attempt in range(max_retries):
                try:
                    timestamp = int(time.time())
                    params = {
                        'partner_id': client_id,
                        'timestamp': timestamp,
                        'access_token': access_token,
                        'shop_id': shop_id,
                        'order_status': 'READY_TO_SHIP',
                        'page_size': 100,
                        'time_range_field': 'create_time',
                        'time_from': time_from,
                        'time_to': time_to,
                        'response_optional_fields': 'order_status'
                    }
                    
                    if cursor:
                        params['cursor'] = cursor

                    path = "/api/v2/order/get_order_list"
                    sign = generate_api_signature(
                        api_type='shop',
                        partner_id=client_id,
                        path=path,
                        timestamp=timestamp,
                        access_token=access_token,
                        shop_id=shop_id,
                        client_secret=client_secret
                    )

                    params['sign'] = sign
                    url = f"https://partner.shopeemobile.com{path}"

                    response = requests.get(url, params=params)
                   
                    if response.status_code == 200:
                        data = response.json()
                        
                        if "error" in data and data["error"]:
                            st.error(f"API Error: {data.get('error', 'Unknown error')} - {data.get('message', '')}")
                            break
                            
                        if "response" in data:
                            page_orders = data["response"].get("order_list", [])
                            all_orders.extend(page_orders)
                            
                            cursor = data["response"].get("next_cursor")
                            has_more = data["response"].get("more", False)
                            
                            break
                        else:
                            st.error("Unexpected API response structure")
                            break
                    else:
                        st.error(f"HTTP Error: {response.status_code} - {response.text}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        break

                except requests.exceptions.RequestException as e:
                    st.error(f"Network error: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    break
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")
                    break

            time.sleep(0.5)
            
            if not cursor:
                has_more = False

    return {"response": {"order_list": all_orders}} if all_orders else None

def get_order_details_bulk(access_token, client_id, client_secret, shop_id, order_sn_list):
    all_order_details = []
    chunk_size = 50

    for i in range(0, len(order_sn_list), chunk_size):
        chunk = order_sn_list[i:i+chunk_size]
        
        timestamp = int(time.time())
        
        params = {
            'partner_id': client_id,
            'timestamp': timestamp,
            'access_token': access_token,
            'shop_id': shop_id,
            'order_sn_list': ",".join(chunk),
            'response_optional_fields': 'item_list, total_amount'
        }

        path = "/api/v2/order/get_order_detail"
        sign = generate_api_signature(
            api_type='shop',
            partner_id=client_id,
            path=path,
            timestamp=timestamp,
            access_token=access_token,
            shop_id=shop_id,
            client_secret=client_secret
        )

        params['sign'] = sign
        url = f"https://partner.shopeemobile.com{path}"
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("response"):
                    all_order_details.extend(data["response"].get("order_list", []))
            else:
                st.error(f"Error fetching details chunk: {response.text}")
            time.sleep(0.1)
        except Exception as e:
            st.error(f"Error fetching details: {str(e)}")
            return None

    return {"response": {"order_list": all_order_details}} if all_order_details else None

def main():
    st.set_page_config(page_title="Shopee Order Management", layout="wide")
    
    # Initialize database
    db = OrderDatabase()
    db.init_tables()
    
    # Initialize session states
    if "authentication_state" not in st.session_state:
        st.session_state.authentication_state = "initial"
    if "orders" not in st.session_state:
        st.session_state.orders = []
    if "order_details" not in st.session_state:
        st.session_state.order_details = []
    if "orders_need_refresh" not in st.session_state:
        st.session_state.orders_need_refresh = True
    if "orders_df" not in st.session_state:
        st.session_state.orders_df = pd.DataFrame()
    if "edited_rows" not in st.session_state:
        st.session_state.edited_rows = {}

    # Sidebar for controls and filters
    with st.sidebar:
        st.header("Controls")
        if st.session_state.get("authentication_state") == "complete":
            if st.button("🔄 Refresh Orders"):
                st.session_state.orders_need_refresh = True
                st.session_state.order_details = []
                st.session_state.orders_df = pd.DataFrame()  # Reset DataFrame
                st.rerun()
            
            st.divider()
            st.subheader("Filters")
            status_filter = st.selectbox(
                "Order Status",
                ["All", "UNPAID", "READY_TO_SHIP", "SHIPPED", "COMPLETED", "CANCELLED"]
            )
            show_preorders_only = st.checkbox("Show Preorders Only")
            st.divider()
            
            if st.button("🚪 Logout"):
                clear_token()
                st.session_state.clear()
                st.rerun()

    # Main content area
    st.title("📦 Shopee Order Management")
    
    # Authentication flow
    if st.session_state.authentication_state != "complete":
        st.info("Please authenticate with your Shopee account to continue.")
        auth_url = get_auth_url()
        st.markdown(f"[🔐 Authenticate with Shopee]({auth_url})")
        
        if "code" in st.query_params:
            with st.spinner("Authenticating..."):
                try:
                    code = st.query_params["code"]
                    token = fetch_token(code)
                    save_token(token)
                    st.session_state.authentication_state = "complete"
                    st.query_params.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
                    clear_token()
    else:
        token = load_token()
        if not token or "access_token" not in token:
            st.error("Token not found or invalid")
            st.session_state.authentication_state = "initial"
            st.rerun()
        
        # Fetch orders and details when needed
        if st.session_state.orders_need_refresh:
            with st.spinner("Fetching orders..."):
                orders_response = get_orders(
                    access_token=token["access_token"],
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    shop_id=SHOP_ID
                )
                
                if orders_response and "response" in orders_response:
                    st.session_state.orders = orders_response["response"].get("order_list", [])
                    
                    if st.session_state.orders:
                        order_sn_list = [o["order_sn"] for o in st.session_state.orders]
                        details_response = get_order_details_bulk(
                            access_token=token["access_token"],
                            client_id=CLIENT_ID,
                            client_secret=CLIENT_SECRET,
                            shop_id=SHOP_ID,
                            order_sn_list=order_sn_list
                        )
                        if details_response and "response" in details_response:
                            order_details_list = details_response["response"].get("order_list", [])
                            order_details_list.sort(key=lambda x: x['create_time'], reverse=True)
                            st.session_state.order_details = order_details_list
                        else:
                            st.session_state.order_details = []
                    else:
                        st.session_state.order_details = []
                    
                    # Build orders_df once after fetching
                    orders_data = []
                    tracking_data = {
                        (item['order_sn'], item['product_name']): item 
                        for item in db.get_order_tracking()
                    }
                    
                    for order_detail in st.session_state.order_details:
                        if "item_list" in order_detail:
                            for item in order_detail["item_list"]:
                                tracking = tracking_data.get(
                                    (order_detail["order_sn"], item["item_name"]), 
                                    {'received': False, 'missing_count': 0, 'note': ''}
                                )
                                orders_data.append({
                                    "Order Number": order_detail["order_sn"],
                                    "Created": datetime.fromtimestamp(order_detail["create_time"]).strftime("%Y-%m-%d %H:%M"),
                                    "Product": item["item_name"],
                                    "Quantity": item["model_quantity_purchased"],
                                    "Image": item["image_info"]["image_url"],
                                    "Received": tracking['received'],
                                    "Missing": tracking['missing_count'],
                                    "Note": tracking['note']
                                })
                    
                    st.session_state.orders_df = pd.DataFrame(orders_data)
                    st.session_state.orders_need_refresh = False
                else:
                    st.error("Failed to fetch orders")

        # Display orders from session state
        if not st.session_state.orders_df.empty:
            # Configure editable columns
            column_config = {
                "Image": st.column_config.ImageColumn("Image", width="small"),
                "Received": st.column_config.CheckboxColumn("Received", width="small"),
                "Missing": st.column_config.NumberColumn("Missing", width="small"),
                "Note": st.column_config.TextColumn("Note", width="medium")
            }

            # Use data_editor to allow edits
            edited_df = st.data_editor(
                st.session_state.orders_df,
                column_config=column_config,
                use_container_width=True,
                key="orders_editor",
                num_rows="fixed",
                height=600
            )

            # Save changes to the database when the user clicks the "Save Changes" button
            if st.button("💾 Save Changes"):
                edited_rows = st.session_state.orders_editor["edited_rows"]
                for idx, changes in edited_rows.items():
                    row = edited_df.iloc[idx]
                    db.upsert_order_tracking(
                        order_sn=str(row["Order Number"]),
                        product_name=str(row["Product"]),
                        received=bool(row["Received"]),  # Convert to native bool
                        missing_count=int(row["Missing"]),  # Convert to native int
                        note=str(row["Note"])  # Ensure note is a string
                    )
                st.success("Changes saved to the database!")

            # Summary statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Orders", len(edited_df["Order Number"].unique()))
            with col2:
                st.metric("Received Items", edited_df["Received"].sum())
            with col3:
                st.metric("Missing Items", edited_df["Missing"].sum())

            # Export to CSV
            if st.button("📥 Export CSV"):
                edited_df.to_csv("shopee_orders.csv", index=False)
                st.success("Orders exported to shopee_orders.csv")
            else:
                st.info("No orders match the current filters.")
        else:
            st.info("No orders found in the selected time range.")

if __name__ == "__main__":
    main()