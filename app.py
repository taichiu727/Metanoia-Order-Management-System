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
    
    def get_order_tracking(self):
        """Fetch all order tracking records from the database"""
        try:
            self.connect()
            self.cursor.execute("""
                SELECT 
                    order_sn,
                    product_name,
                    received,
                    missing_count,
                    note
                FROM order_tracking
            """)
            return self.cursor.fetchall()
        finally:
            self.close()
    
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
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_tags (
                    item_sku VARCHAR(100),
                    tag_name TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (item_sku)
                )
            """)
            self.cursor.execute("""
                DO $$ 
                BEGIN 
                    BEGIN
                        ALTER TABLE shopee_token 
                        ADD COLUMN refresh_token_expire_in BIGINT,
                        ADD COLUMN refresh_token_fetch_time BIGINT;
                    EXCEPTION
                        WHEN duplicate_column THEN 
                            NULL;
                    END;
                END $$;
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
                    shop_id, merchant_id, refresh_token_expire_in,
                    refresh_token_fetch_time, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expire_in = EXCLUDED.expire_in,
                    fetch_time = EXCLUDED.fetch_time,
                    shop_id = EXCLUDED.shop_id,
                    merchant_id = EXCLUDED.merchant_id,
                    refresh_token_expire_in = EXCLUDED.refresh_token_expire_in,
                    refresh_token_fetch_time = EXCLUDED.refresh_token_fetch_time,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                token_data["access_token"],
                token_data["refresh_token"],
                token_data["expire_in"],
                token_data.get("fetch_time", int(time.time())),
                token_data.get("shop_id", SHOP_ID),
                token_data.get("merchant_id"),
                token_data.get("refresh_token_expire_in", 365 * 24 * 60 * 60),  # Default 1 year
                token_data.get("refresh_token_fetch_time", int(time.time())),
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
    def upsert_product_tag(self, item_sku, tag_name):
        try:
            self.connect()
            self.cursor.execute("""
                INSERT INTO product_tags (item_sku, tag_name, last_updated)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (item_sku) 
                DO UPDATE SET 
                    tag_name = EXCLUDED.tag_name,
                    last_updated = CURRENT_TIMESTAMP
            """, (item_sku, tag_name))
            self.conn.commit()
        finally:
            self.close()
    def batch_upsert_order_tracking(self, records):
        try:
            self.connect()
            # Add transaction management
            with self.conn:
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
        except psycopg2.Error as e:
            st.error(f"Database error: {str(e)}")
            raise
        finally:
            self.close()
    def get_product_tags(self):
        try:
            self.connect()
            self.cursor.execute("SELECT item_sku, tag_name FROM product_tags")
            return {row['item_sku']: row['tag_name'] for row in self.cursor.fetchall()}
        finally:
            self.close()


def get_products(access_token, client_id, client_secret, shop_id, offset=0, page_size=50, search_keyword=""):
    """Fetch products from Shopee API"""
    timestamp = int(time.time())
    
    params = {
        'partner_id': client_id,
        'timestamp': timestamp,
        'access_token': access_token,
        'shop_id': shop_id,
        'offset': offset,
        'page_size': page_size,
        'item_status': 'NORMAL'
    }
    
    if search_keyword:
        params['keyword'] = search_keyword

    path = "/api/v2/product/get_item_list"
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
            return response.json()
        else:
            st.error(f"Error fetching products: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error fetching products: {str(e)}")
        return None

def get_item_base_info(access_token, client_id, client_secret, shop_id, item_ids):
    """Fetch detailed item information from Shopee API"""
    timestamp = int(time.time())
    
    params = {
        'partner_id': client_id,
        'timestamp': timestamp,
        'access_token': access_token,
        'shop_id': shop_id,
        'item_id_list': item_ids,
        'need_tax_info': False,
        'need_complaint_policy': False
    }

    path = "/api/v2/product/get_item_base_info"
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
            return response.json()
        else:
            st.error(f"Error fetching item details: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error fetching item details: {str(e)}")
        return None

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
    if "viewport_height" not in st.session_state:
        st.session_state.viewport_height = 800  # Default fallback height
        
    # Add JavaScript to get actual viewport height
    st.markdown(
        """
        <script>
        // Send viewport height to Streamlit
        window.addEventListener('load', function() {
            window.parent.addEventListener('message', function(e) {
                if (e.data.viewport_height) {
                    var height = e.data.viewport_height;
                    window.parent.postMessage({
                        type: "streamlit:setComponentValue",
                        value: height
                    }, "*");
                }
            });
            window.parent.postMessage({
                type: "streamlit:getViewportHeight"
            }, "*");
        });
        </script>
        """,
        unsafe_allow_html=True
    )
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
    
    # Initialize all required session state variables
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
    if "show_stats" not in st.session_state:
        st.session_state.show_stats = False
    if "status_filter" not in st.session_state:
        st.session_state.status_filter = "All"
    if "show_preorders" not in st.session_state:
        st.session_state.show_preorders = False


def initialize_product_state():
    """Initialize product-related session state variables"""
    if "product_page" not in st.session_state:
        st.session_state.product_page = 1
    if "product_search" not in st.session_state:
        st.session_state.product_search = ""
    if "product_tags" not in st.session_state:
        st.session_state.product_tags = {}
    if "all_products_df" not in st.session_state:
        st.session_state.all_products_df = None

def on_data_change():
    """Handle changes in the data editor"""
    if "orders_editor" not in st.session_state:
        return
        
    try:
        # Get edited data
        editor_data = st.session_state.orders_editor
        
        # Check if we have edited rows
        if "edited_rows" not in editor_data:
            return
            
        edited_rows = editor_data["edited_rows"]
        if not edited_rows:
            return
            
        db = OrderDatabase()
        original_df = st.session_state.orders_df
        
        # Process each edited row
        for row_idx_str, changes in edited_rows.items():
            row_idx = int(row_idx_str)
            original_row = original_df.iloc[row_idx]
            
            # Get original values
            order_sn = original_row["Order Number"]
            product_name = original_row["Product"]
            
            # Get updated values, falling back to original if not changed
            received = changes.get("Received", original_row["Received"])
            missing = changes.get("Missing", original_row["Missing"])
            note = changes.get("Note", original_row["Note"])
            
            # Save to database
            db.upsert_order_tracking(
                order_sn=str(order_sn),
                product_name=str(product_name),
                received=bool(received),
                missing_count=int(missing) if pd.notna(missing) else 0,
                note=str(note) if pd.notna(note) else ""
            )
            
            # Update the DataFrame in session state
            st.session_state.orders_df.at[row_idx, "Received"] = received
            st.session_state.orders_df.at[row_idx, "Missing"] = missing
            st.session_state.orders_df.at[row_idx, "Note"] = note
            
        st.toast("✅ Changes saved!")
            
    except Exception as e:
        st.error(f"Error saving changes: {str(e)}")


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
                        "Deadline": datetime.fromtimestamp(order_detail["ship_by_date"]).strftime("%Y-%m-%d %H:%M"),
                        "Product": item["item_name"],
                        "Quantity": item["model_quantity_purchased"],
                        "Image": item["image_info"]["image_url"],
                        "Item Spec": item["model_name"],
                        "Item Number": item["item_sku"],
                        "Received": tracking['received'],
                        "Missing": tracking['missing_count'],
                        "Note": tracking['note']
                    })
        
        return pd.DataFrame(orders_data)

def handle_data_editor_changes(edited_df, db):
    """Handle changes made in the data editor"""
    if st.session_state.last_edited_df is not None:
        changes = []
        for idx, row in edited_df.iterrows():
            last_row = st.session_state.last_edited_df.iloc[idx]
            if (row[["Received", "Missing", "Note"]] != last_row[["Received", "Missing", "Note"]]).any():
                changes.append((str(row["Order Number"]), str(row["Product"]), bool(row["Received"]), int(row["Missing"]), str(row["Note"])))
        
        if changes:
            db.batch_upsert_order_tracking(changes)
            st.session_state.orders_df = update_orders_df(st.session_state.orders_df, edited_df)
            st.session_state.last_edited_df = edited_df.copy()
            st.toast("Changes saved!")
    else:
        st.session_state.last_edited_df = edited_df.copy()

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
                    #st.rerun()
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
    
    # Check refresh token expiration first
    refresh_token_expire_in = token.get("refresh_token_expire_in", 365 * 24 * 60 * 60)  # Default 1 year
    refresh_token_fetch_time = token.get("refresh_token_fetch_time", token["fetch_time"])
    refresh_token_expiration = refresh_token_fetch_time + refresh_token_expire_in
    
    # If refresh token is expired, clear token and require re-authentication
    if current_time >= refresh_token_expiration:
        db.clear_token()
        return None
    
    # Check access token expiration
    access_token_expiration = token["fetch_time"] + token["expire_in"]
    
    # If access token expires in less than 5 minutes or is expired, refresh it
    if (access_token_expiration - current_time) < 300:
        try:
            new_token_data = refresh_token(token["refresh_token"])
            if new_token_data:
                new_token = {
                    "access_token": new_token_data["access_token"],
                    "refresh_token": new_token_data["refresh_token"],
                    "expire_in": new_token_data["expire_in"],
                    "fetch_time": current_time,
                    "shop_id": SHOP_ID,
                    "merchant_id": new_token_data.get("merchant_id"),
                    # Preserve refresh token expiration information
                    "refresh_token_expire_in": refresh_token_expire_in,
                    "refresh_token_fetch_time": refresh_token_fetch_time
                }
                db.save_token(new_token)
                return new_token
        except Exception as e:
            st.error(f"Failed to refresh token: {str(e)}")
            # Only clear token if refresh token is expired or invalid
            if "Token invalid" in str(e) or "refresh_token_expired" in str(e):
                db.clear_token()
            return None
    
    return token

def update_orders_df(original_df, edited_df):
    """Update the main orders DataFrame with edited changes while preserving column order"""
    # Store original column order
    column_order = original_df.columns.tolist()
    
    # Perform update
    update_cols = ["Received", "Missing", "Note"]
    updated_df = original_df.set_index(['Order Number', 'Product']).combine_first(
        edited_df.set_index(['Order Number', 'Product'])[update_cols]
    ).reset_index()
    
    # Reorder columns to match original order
    return updated_df[column_order]

@st.fragment
def sidebar_controls():
    """Fragment for sidebar controls"""
    st.header("Controls")
    if st.session_state.authentication_state == "complete":
        if st.button("🔄 Refresh Orders"):
            st.session_state.orders_need_refresh = True
            st.session_state.order_details = []
            st.session_state.orders_df = pd.DataFrame()
            st.session_state.last_edited_df = None
            st.rerun()  # Full rerun needed for data refresh
        
        st.divider()
        st.subheader("Filters")
        status_filter = st.selectbox(
            "Order Status",
            ["All", "UNPAID", "READY_TO_SHIP", "SHIPPED", "COMPLETED", "CANCELLED"],
            key="status_filter"
        )
        show_preorders_only = st.checkbox("Show Preorders Only", key="show_preorders")
        
        st.divider()
        if st.button("📊 View Statistics"):
            st.session_state.show_stats = not st.session_state.get('show_stats', False)
            st.rerun(scope="fragment")
        
        st.divider()
        if st.button("🚪 Logout"):
            db = OrderDatabase()
            db.clear_token()
            st.session_state.clear()
            st.rerun()

@st.fragment
def orders_table(filtered_df):
    if filtered_df.empty:
        return filtered_df

    db = OrderDatabase()
    product_tags = db.get_product_tags()
    filtered_df['Tag'] = filtered_df['Item Number'].map(lambda x: product_tags.get(x, ''))

    orders = filtered_df.groupby('Order Number')
    all_edited_data = []
    
    for order_num, order_data in orders:
        all_received = all(order_data['Received'])
        status_emoji = "✅" if all_received else "⚠️" if any(order_data['Received']) else "❌"
        
        with st.expander(f"Order: {order_num} {status_emoji}", expanded=True):
            column_config = {
                "Order Number": st.column_config.TextColumn("Order Number", width="small"),
                "Created": st.column_config.TextColumn("Created", width="small"),
                "Deadline": st.column_config.TextColumn("Deadline", width="small"),
                "Product": st.column_config.TextColumn("Product", width="medium"),
                "Item Spec": st.column_config.TextColumn("Item Spec", width="small"),
                "Item Number": st.column_config.TextColumn("Item Number", width="small"),
                "Quantity": st.column_config.NumberColumn("Quantity", width="small"),
                "Image": st.column_config.ImageColumn("Image", width="small"),
                "Tag": st.column_config.TextColumn("Tag", width="small"),
                "Received": st.column_config.CheckboxColumn("Received", width="small", default=False),
                "Missing": st.column_config.NumberColumn("Missing", width="small", default=0),
                "Note": st.column_config.TextColumn("Note", width="medium", default="")
            }
            
            product_df = order_data[["Order Number", "Created", "Deadline", "Product", 
                                   "Item Spec", "Item Number", "Quantity", "Image", 
                                   "Received", "Missing", "Note", "Tag"]]
            edited_df = st.data_editor(
                product_df,
                column_config=column_config,
                use_container_width=True,
                key=f"order_{order_num}",
                num_rows="fixed",
                disabled=["Order Number", "Created", "Deadline", "Product", 
                         "Item Spec", "Item Number", "Quantity", "Image", "Tag"]
            )
            
            if edited_df is not None:
                all_edited_data.append(edited_df)

    if all_edited_data:
        combined_edits = pd.concat(all_edited_data)
        filtered_df = filtered_df.copy()
        for idx, row in combined_edits.iterrows():
            mask = (filtered_df['Order Number'] == row['Order Number']) & (filtered_df['Product'] == row['Product'])
            filtered_df.loc[mask, 'Received'] = row['Received'] if pd.notna(row['Received']) else False
            filtered_df.loc[mask, 'Missing'] = row['Missing'] if pd.notna(row['Missing']) else 0
            filtered_df.loc[mask, 'Note'] = row['Note'] if pd.notna(row['Note']) else ""

    return filtered_df

@st.fragment
def statistics_view(df):
    """Fragment for statistics display"""
    if st.session_state.get('show_stats', False):
        st.subheader("📊 Order Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Orders", len(df["Order Number"].unique()))
        with col2:
            st.metric("Total Items", df["Quantity"].sum())
        with col3:
            st.metric("Received Items", df["Received"].sum())
        with col4:
            st.metric("Missing Items", df["Missing"].sum())
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Missing Items by Product")
            missing_by_product = (
                df[df["Missing"] > 0]
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
            pending_receipts = df[~df["Received"]].groupby("Product")["Quantity"].sum()
            if not pending_receipts.empty:
                st.dataframe(pending_receipts)
            else:
                st.info("No pending receipts")

@st.fragment
def export_controls(df):
    """Fragment for export functionality"""
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Export to CSV"):
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"shopee_orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("📋 Copy to Clipboard"):
            df.to_clipboard(index=False)
            st.success("Data copied to clipboard!")

@st.fragment
def auth_fragment():
    """Fragment for handling authentication"""
    if st.session_state.authentication_state != "complete":
        st.info("Please authenticate with your Shopee account to continue.")
        auth_url = get_auth_url()
        st.markdown(f"[🔐 Authenticate with Shopee]({auth_url})")
        
        if "code" in st.query_params:
            with st.spinner("Authenticating..."):
                try:
                    code = st.query_params["code"]
                    token = fetch_token(code)
                    # Add fetch time and refresh token expiration
                    current_time = int(time.time())
                    token.update({
                        "fetch_time": current_time,
                        "refresh_token_fetch_time": current_time,
                        "refresh_token_expire_in": 365 * 24 * 60 * 60  # 1 year
                    })
                    db.save_token(token)
                    st.session_state.authentication_state = "complete"
                    st.query_params.clear()
                except Exception as e:
                    st.error(f"Authentication failed: {str(e)}")
                    db.clear_token()
                    return False
        return False
    return True

def handle_data_editor_changes(edited_df, db):
    """Handle changes made in the data editor"""
    if st.session_state.last_edited_df is not None:
        changes = []
        for idx, row in edited_df.iterrows():
            last_row = st.session_state.last_edited_df.iloc[idx]
            if (row[["Received", "Missing", "Note"]] != last_row[["Received", "Missing", "Note"]]).any():
                changes.append((
                    str(row["Order Number"]),
                    str(row["Product"]),
                    bool(row["Received"]),
                    int(row["Missing"]) if pd.notna(row["Missing"]) else 0,
                    str(row["Note"]) if pd.notna(row["Note"]) else ""
                ))
        
        if changes:
            try:
                db.batch_upsert_order_tracking(changes)
                st.session_state.last_edited_df = edited_df.copy()
                st.toast("✅ Changes saved!")
            except Exception as e:
                st.error(f"Error saving changes: {str(e)}")
    else:
        st.session_state.last_edited_df = edited_df.copy()







@st.cache_data(ttl=300)
def fetch_all_products(access_token, client_id, client_secret, shop_id):
    """Fetch all products with pagination handling"""
    all_items = []
    page_size = 100
    offset = 0
    
    products_response = get_products(
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        shop_id=shop_id,
        offset=offset,
        page_size=page_size
    )
    
    if not products_response or "response" not in products_response:
        st.error("Failed to get products response")
        return []
        
    items = products_response["response"].get("item", [])
    st.write(f"Debug: Found {len(items)} items in first page")
    
    if not items:
        st.warning("No items found in the shop")
        return []
    
    # Get details in smaller batches
    batch_size = 25  # Even smaller batch size
    for i in range(0, len(items), batch_size):
        batch_items = items[i:i + batch_size]
        item_ids = [str(item["item_id"]) for item in batch_items]
        
        st.write(f"Debug: Getting details for batch {i//batch_size + 1}, {len(item_ids)} items")
        time.sleep(1)  # Add more delay between batches
        
        try:
            details_response = get_item_base_info(
                access_token=access_token,
                client_id=client_id,
                client_secret=client_secret,
                shop_id=shop_id,
                item_ids=item_ids
            )
            
            if details_response and "response" in details_response:
                if "item_list" in details_response["response"]:
                    batch_items = details_response["response"]["item_list"]
                    all_items.extend(batch_items)
                    st.write(f"Debug: Successfully added {len(batch_items)} items")
                else:
                    st.write("Debug: No item_list in response:", details_response["response"])
            else:
                st.write("Debug: Invalid response structure:", details_response)
                
        except Exception as e:
            st.error(f"Error fetching batch {i//batch_size + 1}: {str(e)}")
            continue
            
        time.sleep(0.5)
    
    st.write(f"Debug: Total items collected: {len(all_items)}")
    return all_items

def filter_and_paginate_df(df, search_query, page, page_size):
    """Filter DataFrame and handle pagination"""
    if df is None:
        return None, 0
        
    # Apply search filter
    if search_query:
        search_query = search_query.lower()
        df = df[
            df['Product Name'].str.lower().str.contains(search_query, na=False) |
            df['SKU'].str.lower().str.contains(search_query, na=False)
        ]
    
    total_items = len(df)
    
    # Apply pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    return df.iloc[start_idx:end_idx], total_items

def on_tag_change(edited_rows, current_df, db):
    """Handle tag changes without causing a full rerun"""
    changes_made = False
    
    for idx_str, changes in edited_rows.items():
        if "Tag" in changes:
            idx = int(idx_str)
            sku = current_df.iloc[idx]["SKU"]
            new_tag = str(changes["Tag"]) if pd.notna(changes["Tag"]) else ""
            current_tag = st.session_state.product_tags.get(sku, "")
            
            if new_tag != current_tag:
                db.upsert_product_tag(sku, new_tag)
                st.session_state.product_tags[sku] = new_tag
                changes_made = True
    
    if changes_made:
        st.toast("✅ Tags updated!")


def products_page():
    """Products page with improved error handling"""
    st.title("📦 Products")
    
    # Initialize state
    if "all_products_df" not in st.session_state:
        st.session_state.all_products_df = None
    if "product_page" not in st.session_state:
        st.session_state.product_page = 1
    
    db = OrderDatabase()
    token = db.load_token()
    
    if not token:
        st.error("Please authenticate first")
        return
    
    # Search input
    search = st.text_input(
        "🔍 Search products by name or SKU",
        key="search_input"
    )
    
    # Reset button
    if st.button("🔄 Reset Product List"):
        st.session_state.all_products_df = None
        st.rerun()
    
    # Fetch all products if we don't have them
    if st.session_state.all_products_df is None:
        with st.spinner("Loading products..."):
            items = fetch_all_products(
                token["access_token"],
                CLIENT_ID,
                CLIENT_SECRET,
                SHOP_ID
            )
            
            if items:
                st.write(f"Debug: Processing {len(items)} items into DataFrame")
                # Prepare data for table
                table_data = []
                for item in items:
                    try:
                        # Get the first price info or use defaults
                        price_info = (item.get("price_info") or [{}])[0]
                        
                        # Handle potential missing nested structures
                        stock_info = (
                            item.get("stock_info_v2", {})
                            .get("summary_info", {})
                            .get("total_available_stock", 0)
                        )
                        
                        # Get the first image or use empty string
                        image_url = (
                            item.get("image", {})
                            .get("image_url_list", [""])[0]
                        )
                        
                        table_data.append({
                            "Image": image_url,
                            "Product Name": item.get("item_name", ""),
                            "SKU": item.get("item_sku", ""),
                            "Stock": stock_info,
                            "Price": price_info.get("current_price", 0),
                            "Status": item.get("item_status", ""),
                            "Tag": ""
                        })
                    except Exception as e:
                        st.write(f"Debug: Error processing item: {str(e)}")
                        st.write("Debug: Problem item:", item)
                
                if table_data:
                    st.session_state.all_products_df = pd.DataFrame(table_data)
                    st.write(f"Debug: Created DataFrame with {len(table_data)} rows")
                else:
                    st.error("No data to create DataFrame")
            else:
                st.error("No items returned from fetch_all_products")
    
    # Display products
    if st.session_state.all_products_df is not None and not st.session_state.all_products_df.empty:
        df = st.session_state.all_products_df.copy()
        
        # Load and apply tags
        tags = db.get_product_tags()
        df['Tag'] = df['SKU'].map(lambda x: tags.get(x, ""))
        
        # Apply search filter
        if search:
            search = search.lower()
            df = df[
                df['Product Name'].str.lower().str.contains(search, na=False) |
                df['SKU'].str.lower().str.contains(search, na=False)
            ]
        
        total_items = len(df)
        
        if total_items > 0:
            page_size = 50
            page = st.session_state.product_page
            
            # Apply pagination
            start_idx = (page - 1) * page_size
            end_idx = min(start_idx + page_size, total_items)
            page_df = df.iloc[start_idx:end_idx]
            
            st.write(f"Showing {len(page_df)} of {total_items} products")
            
            # Configure table
            column_config = {
                "Image": st.column_config.ImageColumn("Image", width="small"),
                "Product Name": st.column_config.TextColumn("Product Name", width="medium"),
                "SKU": st.column_config.TextColumn("SKU", width="small"),
                "Stock": st.column_config.NumberColumn("Stock", width="small"),
                "Price": st.column_config.NumberColumn("Price", width="small", format="$%.2f"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Tag": st.column_config.TextColumn("Tag", width="small")
            }
            
            # Display editor
            edited_df = st.data_editor(
                page_df,
                column_config=column_config,
                use_container_width=True,
                num_rows="fixed",
                disabled=["Image", "Product Name", "SKU", "Stock", "Price", "Status"],
                key="products_editor"
            )
            
            # Handle tag changes
            if "edited_rows" in st.session_state.products_editor:
                for idx_str, changes in st.session_state.products_editor["edited_rows"].items():
                    if "Tag" in changes:
                        idx = int(idx_str)
                        sku = page_df.iloc[idx]["SKU"]
                        new_tag = str(changes["Tag"]) if pd.notna(changes["Tag"]) else ""
                        db.upsert_product_tag(sku, new_tag)
                        st.toast("✅ Tags updated!")
            
            # Pagination controls
            total_pages = (total_items + page_size - 1) // page_size
            cols = st.columns(5)
            
            with cols[1]:
                if st.button("⬅️ Previous", disabled=page==1):
                    st.session_state.product_page = max(1, page - 1)
                    st.rerun()
            
            with cols[2]:
                st.write(f"Page {page} of {total_pages}")
                
            with cols[3]:
                if st.button("Next ➡️", disabled=page >= total_pages):
                    st.session_state.product_page = min(total_pages, page + 1)
                    st.rerun()
        else:
            st.info("No products found matching your search.")
    else:
        st.info("No products loaded yet.")


def main():
    st.set_page_config(page_title="Order Management", layout="wide")
    
    db = OrderDatabase()
    db.init_tables()
    initialize_session_state()

    if "product_page" not in st.session_state:
        st.session_state.product_page = 1
    if "product_search" not in st.session_state:
        st.session_state.product_search = ""

    st.title("📦 Order Management")
    
    # Handle authentication using fragment
    if not auth_fragment():
        return

    # Check token validity
    token = check_token_validity(db)
    if not token:
        st.error("Token not found or invalid")
        st.session_state.authentication_state = "initial"
        return

    # Use sidebar fragment within sidebar context
    with st.sidebar:
        sidebar_controls()

    tab1, tab2 = st.tabs(["Orders", "Products"])
    
    with tab1:
        # Fetch and process orders if needed
        if st.session_state.orders_need_refresh:
            st.session_state.orders_df = fetch_and_process_orders(token, db)
            st.session_state.orders_need_refresh = False

        if not st.session_state.orders_df.empty:
            # Apply filters based on session state
            filtered_df = apply_filters(
                st.session_state.orders_df, 
                st.session_state.get('status_filter', 'All'),
                st.session_state.get('show_preorders', False)
            )
            
            # Use fragments for main UI components
            edited_df = orders_table(filtered_df)
            statistics_view(edited_df)
            
            st.divider()
            export_controls(edited_df)
        else:
            st.info("No orders found in the selected time range.")
    
    with tab2:
        products_page()

if __name__ == "__main__":
    main()