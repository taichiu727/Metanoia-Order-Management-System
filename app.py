import streamlit as st
import hmac
import pandas as pd
from shopee_oauth import (
    get_auth_url, 
    fetch_token, 
    refresh_token,
    CLIENT_ID,
    CLIENT_SECRET,
    SHOP_ID
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


            # New shopee_token table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS shopee_token (
                    id SERIAL PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expire_in INTEGER NOT NULL,
                    fetch_time BIGINT NOT NULL,
                    shop_id BIGINT NOT NULL,
                    merchant_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.conn.commit()
        finally:
            self.close()
    
    def save_token(self, token_data):
        try:
            self.connect()
            self.cursor.execute("""
                INSERT INTO shopee_token (
                    access_token, refresh_token, expire_in, fetch_time, 
                    shop_id, merchant_id, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expire_in = EXCLUDED.expire_in,
                    fetch_time = EXCLUDED.fetch_time,
                    shop_id = EXCLUDED.shop_id,
                    merchant_id = EXCLUDED.merchant_id,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                token_data["access_token"],
                token_data["refresh_token"],
                token_data["expire_in"],
                token_data.get("fetch_time", int(time.time())),
                token_data.get("shop_id", SHOP_ID),
                token_data.get("merchant_id"),
            ))
            self.conn.commit()
            return self.cursor.fetchone()["id"]
        finally:
            self.close()

    def load_token(self):
        try:
            self.connect()
            self.cursor.execute("""
                SELECT 
                    access_token, refresh_token, expire_in, fetch_time,
                    shop_id, merchant_id
                FROM shopee_token
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            return self.cursor.fetchone()
        finally:
            self.close()

    def clear_token(self):
        try:
            self.connect()
            self.cursor.execute("TRUNCATE TABLE shopee_token")
            self.conn.commit()
        finally:
            self.close()

    def batch_upsert_order_tracking(self, records):
        try:
            self.connect()
            # Convert boolean values explicitly
            processed_records = [
                (
                    str(record[0]),  # order_sn
                    str(record[1]),  # product_name
                    bool(record[2]),  # received - explicit boolean conversion
                    int(record[3]),  # missing_count
                    str(record[4])   # note
                )
                for record in records
            ]
            
            self.cursor.executemany("""
                INSERT INTO order_tracking (order_sn, product_name, received, missing_count, note, last_updated)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (order_sn, product_name) 
                DO UPDATE SET 
                    received = EXCLUDED.received,
                    missing_count = EXCLUDED.missing_count,
                    note = EXCLUDED.note,
                    last_updated = CURRENT_TIMESTAMP
            """, processed_records)
            self.conn.commit()
        finally:
            self.close()

    def batch_upsert_order_tracking(self, records):
        try:
            self.connect()
            self.cursor.executemany("""
                INSERT INTO order_tracking (order_sn, product_name, received, missing_count, note, last_updated)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (order_sn, product_name) 
                DO UPDATE SET 
                    received = EXCLUDED.received,
                    missing_count = EXCLUDED.missing_count,
                    note = EXCLUDED.note,
                    last_updated = CURRENT_TIMESTAMP
            """, records)
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

def generate_api_signature(api_type, partner_id, path, timestamp, access_token, shop_id, client_secret):
    """Generate Shopee API signature"""
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
    """Fetch orders from Shopee API"""
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

            if not cursor:
                has_more = False
            time.sleep(0.5)

    return {"response": {"order_list": all_orders}} if all_orders else None

def get_order_details_bulk(access_token, client_id, client_secret, shop_id, order_sn_list):
    """Fetch order details in bulk from Shopee API"""
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

def initialize_session_state():
    """Initialize all session state variables"""
    if "authentication_state" not in st.session_state:
        st.session_state.authentication_state = "initial"
        # Check for existing valid token
        db = OrderDatabase()
        token = db.load_token()
        if token:
            current_time = int(time.time())
            token_age = current_time - token["fetch_time"]
            if token_age < (token["expire_in"] - 300):  # Token is still valid
                st.session_state.authentication_state = "complete"
    
    if "orders" not in st.session_state:
        st.session_state.orders = []
    if "order_details" not in st.session_state:
        st.session_state.order_details = []
    if "orders_need_refresh" not in st.session_state:
        st.session_state.orders_need_refresh = True
    if "orders_df" not in st.session_state:
        st.session_state.orders_df = pd.DataFrame()
    if "last_edited_df" not in st.session_state:
        st.session_state.last_edited_df = None
    if "pending_changes" not in st.session_state:
        st.session_state.pending_changes = False


def handle_authentication():
    """Handle the Shopee authentication flow"""
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
        return False
    return True

def fetch_and_process_orders(token, db):
    """Fetch orders and process them into a DataFrame"""
    with st.spinner("Fetching orders..."):
        orders_response = get_orders(
            access_token=token["access_token"],
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            shop_id=SHOP_ID
        )
        
        if not orders_response or "response" not in orders_response:
            st.error("Failed to fetch orders")
            return pd.DataFrame()

        st.session_state.orders = orders_response["response"].get("order_list", [])
        
        if not st.session_state.orders:
            return pd.DataFrame()

        order_sn_list = [o["order_sn"] for o in st.session_state.orders]
        details_response = get_order_details_bulk(
            access_token=token["access_token"],
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            shop_id=SHOP_ID,
            order_sn_list=order_sn_list
        )

        if not details_response or "response" not in details_response:
            return pd.DataFrame()

        order_details_list = details_response["response"].get("order_list", [])
        order_details_list.sort(key=lambda x: x['create_time'], reverse=True)
        st.session_state.order_details = order_details_list

        # Process orders into DataFrame
        tracking_data = {
            (item['order_sn'], item['product_name']): item 
            for item in db.get_order_tracking()
        }
        
        orders_data = []
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
                        "Item Number": item["item_sku"],
                        "Received": tracking['received'],
                        "Missing": tracking['missing_count'],
                        "Note": tracking['note']
                    })
        
        return pd.DataFrame(orders_data)

def handle_data_editor_changes(edited_df, db):
    """Handle changes made in the data editor with improved change detection"""
    if st.session_state.last_edited_df is not None:
        changes = []
        
        # Convert DataFrames to dictionaries for easier comparison
        current_state = edited_df.set_index(['Order Number', 'Product']).to_dict('index')
        previous_state = st.session_state.last_edited_df.set_index(['Order Number', 'Product']).to_dict('index')
        
        # Compare current and previous states
        for (order_number, product), current_row in current_state.items():
            previous_row = previous_state.get((order_number, product), {})
            
            # Check if any of the editable fields have changed
            if (
                current_row.get('Received') != previous_row.get('Received') or
                current_row.get('Missing') != previous_row.get('Missing') or
                current_row.get('Note') != previous_row.get('Note')
            ):
                changes.append((
                    str(order_number),
                    str(product),
                    bool(current_row['Received']),  # Explicit boolean conversion
                    int(current_row['Missing']),
                    str(current_row['Note'])
                ))
        
        if changes:
            try:
                db.batch_upsert_order_tracking(changes)
                st.session_state.last_edited_df = edited_df.copy()
                st.toast("Changes saved successfully!")
                return True
            except Exception as e:
                st.error(f"Error saving changes: {str(e)}")
                return False
    
    st.session_state.last_edited_df = edited_df.copy()
    return False

def apply_filters(df, status_filter, show_preorders_only):
    """Apply filters to the DataFrame"""
    filtered_df = df.copy()
    
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df["Status"] == status_filter]
    
    if show_preorders_only:
        filtered_df = filtered_df[filtered_df["Is_Preorder"]]
    
    return filtered_df

def handle_authentication(db):
    """Handle the Shopee authentication flow using database storage"""
    # First check if there's a valid token in the database
    token = check_token_validity(db)
    if token:
        st.session_state.authentication_state = "complete"
        return True
        
    if st.session_state.authentication_state != "complete":
        st.info("Please authenticate with your Shopee account to continue.")
        auth_url = get_auth_url()
        st.markdown(f"[🔐 Authenticate with Shopee]({auth_url})")
        
        if "code" in st.query_params:
            with st.spinner("Authenticating..."):
                try:
                    code = st.query_params["code"]
                    token = fetch_token(code)
                    # Add fetch time to token data
                    token["fetch_time"] = int(time.time())
                    db.save_token(token)
                    st.session_state.authentication_state = "complete"
                    st.query_params.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
                    db.clear_token()
                    return False
        return False
    return True

def check_token_validity(db):
    """Check if the stored token is valid and refresh if needed"""
    token = db.load_token()
    if not token:
        return None
    
    current_time = int(time.time())
    token_age = current_time - token["fetch_time"]
    
    # If token is expired or close to expiring, try to refresh it
    if token_age > (token["expire_in"] - 300):  # Refresh if less than 5 minutes remaining
        try:
            new_token_data = refresh_token(token["refresh_token"])
            if new_token_data:
                new_token = {
                    "access_token": new_token_data["access_token"],
                    "refresh_token": new_token_data["refresh_token"],
                    "expire_in": new_token_data["expire_in"],
                    "fetch_time": current_time,
                    "shop_id": SHOP_ID,
                    "merchant_id": new_token_data.get("merchant_id")
                }
                db.save_token(new_token)
                return new_token
        except Exception as e:
            st.error(f"Failed to refresh token: {str(e)}")
            db.clear_token()
            return None
    
    return token

def main():
    st.set_page_config(page_title="Shopee Order Management", layout="wide")
    
    # Initialize database and session state
    db = OrderDatabase()
    db.init_tables()
    initialize_session_state()

    status_filter = "ALL"
    show_preorders_only = False
   
   column_config = {
        "Order Number": st.column_config.TextColumn(
            "Order Number",
            width="small",
            help="Shopee order number"
        ),
        "Created": st.column_config.TextColumn(
            "Created",
            width="small",
            help="Order creation date and time"
        ),
        "Product": st.column_config.TextColumn(
            "Product",
            width="small",
            help="Product name"
        ),
        "Quantity": st.column_config.NumberColumn(
            "Quantity",
            width="small",
            help="Ordered quantity"
        ),
        "Image": st.column_config.ImageColumn(
            "Image",
            width="small",
            help="Product image"
        ),
        "Item Number": st.column_config.TextColumn(
            "Item Number",
            width="small",
            help="Item Number"
        ),
        "Received": st.column_config.CheckboxColumn(
            "Received",
            width="small",
            help="Mark if item has been received"
        ),
        "Missing": st.column_config.NumberColumn(
            "Missing",
            width="small",
            help="Number of missing items"
        ),
        "Note": st.column_config.TextColumn(
            "Note",
            width="medium",
            help="Additional notes"
        )
    }
    
    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        if st.session_state.authentication_state == "complete":
            if st.button("🔄 Refresh Orders"):
                st.session_state.orders_need_refresh = True
                st.session_state.order_details = []
                st.session_state.orders_df = pd.DataFrame()
                st.session_state.last_edited_df = None
                st.rerun()
            
            st.divider()
            st.subheader("Filters")
            status_filter = st.selectbox(
                "Order Status",
                ["All", "UNPAID", "READY_TO_SHIP", "SHIPPED", "COMPLETED", "CANCELLED"]
            )
            show_preorders_only = st.checkbox("Show Preorders Only")
            
            st.divider()
            if st.button("📊 View Statistics"):
                st.session_state.show_stats = not st.session_state.get('show_stats', False)
            
            st.divider()
            if st.button("🚪 Logout"):
                clear_token()
                st.session_state.clear()
                st.rerun()

    # Main content
    st.title("📦 Shopee Order Management")
    
    # Handle authentication
    if not handle_authentication(db):
        return

    # Check token validity
    token = check_token_validity(db)
    if not token:
        st.error("Token not found or invalid")
        st.session_state.authentication_state = "initial"
        st.rerun()

    # Fetch and display orders
    if st.session_state.orders_need_refresh:
        st.session_state.orders_df = fetch_and_process_orders(token, db)
        st.session_state.orders_need_refresh = False

    if not st.session_state.orders_df.empty:
        # Configure the data editor with explicit onChange handling
        filtered_df = apply_filters(st.session_state.orders_df, status_filter, show_preorders_only)
        edited_df = st.data_editor(
            filtered_df,
            column_config=column_config,
            use_container_width=True,
            key="orders_editor",
            num_rows="fixed",
            height=600,
            disabled=False,  # Ensure editing is enabled
            on_change=lambda: setattr(st.session_state, 'pending_changes', True)
        )

        # Handle changes when detected
        if st.session_state.pending_changes:
            if handle_data_editor_changes(edited_df, db):
                st.session_state.pending_changes = False
                st.experimental_rerun()

        # Statistics and Metrics
        if st.session_state.get('show_stats', False):
            st.subheader("📊 Order Statistics")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Orders", len(edited_df["Order Number"].unique()))
            with col2:
                st.metric("Total Items", edited_df["Quantity"].sum())
            with col3:
                st.metric("Received Items", edited_df["Received"].sum())
            with col4:
                st.metric("Missing Items", edited_df["Missing"].sum())
            
            # Additional statistics
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Missing Items by Product")
                missing_by_product = (
                    edited_df[edited_df["Missing"] > 0]
                    .groupby("Product")["Missing"]
                    .sum()
                    .sort_values(ascending=False)
                )
                if not missing_by_product.empty:
                    st.dataframe(missing_by_product)
                else:
                    st.info("No missing items reported")
            
            with col2:
                st.subheader("Pending Receipts")
                pending_receipts = edited_df[~edited_df["Received"]].groupby("Product")["Quantity"].sum()
                if not pending_receipts.empty:
                    st.dataframe(pending_receipts)
                else:
                    st.info("No pending receipts")

        # Export functionality
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Export to CSV"):
                csv = edited_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"shopee_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📋 Copy to Clipboard"):
                edited_df.to_clipboard(index=False)
                st.success("Data copied to clipboard!")
    else:
        st.info("No orders found in the selected time range.")

if __name__ == "__main__":
    main()