import hmac
import hashlib
import requests
import time
from urllib.parse import quote
import json
import base64
import re
import streamlit as st

# ECPay Environment Configuration
ECPAY_ENV = "production"  # Change to "production" for live environment
ECPAY_CONFIG = {
    "test": {
        "create_order": "https://logistics-stage.ecpay.com.tw/Express/Create",
        "print_unimart_c2c": "https://logistics-stage.ecpay.com.tw/Express/PrintUniMartC2COrderInfo",
        "query_logistics": "https://logistics-stage.ecpay.com.tw/Helper/QueryLogisticsTradeInfo/V5",
        "print_fami_c2c": "https://logistics-stage.ecpay.com.tw/Express/PrintFAMIC2COrderInfo"
    },
    "production": {
        "create_order": "https://logistics.ecpay.com.tw/Express/Create",
        "print_unimart_c2c": "https://logistics.ecpay.com.tw/Express/PrintUniMartC2COrderInfo",
        "query_logistics": "https://logistics.ecpay.com.tw/Helper/QueryLogisticsTradeInfo/V5",
        "print_fami_c2c": "https://logistics.ecpay.com.tw/Express/PrintFAMIC2COrderInfo"
    }
}

# These should be stored in st.secrets or environment variables in production
ECPAY_MERCHANT_ID = ""  # Your ECPay merchant ID
ECPAY_HASH_KEY = ""     # Your ECPay hash key
ECPAY_HASH_IV = ""      # Your ECPay hash IV

def set_ecpay_credentials(merchant_id, hash_key, hash_iv, environment="test"):
    """Set ECPay credentials globally"""
    global ECPAY_MERCHANT_ID, ECPAY_HASH_KEY, ECPAY_HASH_IV, ECPAY_ENV
    ECPAY_MERCHANT_ID = merchant_id
    ECPAY_HASH_KEY = hash_key
    ECPAY_HASH_IV = hash_iv
    ECPAY_ENV = environment

class ECPayLogistics:
    """Class to handle ECPay logistics API operations"""
    
    @staticmethod
    def create_check_mac_value(params):
        """Generate CheckMacValue for ECPay API following their exact process"""
        if not ECPAY_HASH_KEY or not ECPAY_HASH_IV:
            raise ValueError("ECPay credentials not set. Call set_ecpay_credentials() first.")
        
        # Step 1: Sort parameters alphabetically
        # Note: Exclude CheckMacValue if it exists
        sorted_params = {}
        for key in sorted(params.keys()):
            if key != "CheckMacValue":
                sorted_params[key] = params[key]
        
        # Step 2: Create a string with HashKey at beginning and HashIV at end
        # Format: HashKey=key&param1=value1&param2=value2&...&paramN=valueN&HashIV=iv
        stringified = "HashKey=" + ECPAY_HASH_KEY
        for key, value in sorted_params.items():
            stringified += "&" + key + "=" + str(value)
        stringified += "&HashIV=" + ECPAY_HASH_IV
        
        # Step 3: URL encode the entire string
        # ECPay requires specific URL encoding where spaces are encoded as '+'
        from urllib.parse import quote_plus
        encoded = quote_plus(stringified)
        
        # Step 4: Convert to lowercase
        encoded = encoded.lower()
        
        # Step 5: Apply MD5 hash
        import hashlib
        hashed = hashlib.md5(encoded.encode('utf-8')).hexdigest()
        
        # Step 6: Convert to uppercase
        check_mac_value = hashed.upper()
        
        # Debug output
        print(f"Original params: {params}")
        print(f"Sorted params: {sorted_params}")
        print(f"Pre-encoded string: {stringified}")
        print(f"URL-encoded string: {encoded}")
        print(f"Generated CheckMacValue: {check_mac_value}")
        
        return check_mac_value
    
    @staticmethod
    def create_logistics_order(order_data):
        """Create a new logistics order with ECPay"""
        # Generate a default order number if not provided
        merchant_trade_no = order_data.get("MerchantTradeNo", "ORDER")
        
        # Sanitize receiver name (max 5 Chinese chars or 10 English chars)
        receiver_name = order_data.get("ReceiverName", "")
        if len(receiver_name) > 10:
            receiver_name = receiver_name[:10]
        
        # VERY STRICT sanitizing of goods name - keep it extremely short
        goods_name = order_data.get("GoodsName", "")
        # First remove emoji and special characters
        import re
        goods_name = re.sub(r'[^\w\s\u4e00-\u9fff,.]', '', goods_name)
        # Then limit to no more than 25 characters (much shorter than the limit)
        if len(goods_name) > 25:
            goods_name = goods_name[:22] + "..."
        
        # Prepare API parameters with strict cleaning
        params = {
            "MerchantID": ECPAY_MERCHANT_ID,
            "MerchantTradeNo": merchant_trade_no,
            "MerchantTradeDate": order_data.get("MerchantTradeDate", ""),
            "LogisticsType": order_data.get("LogisticsType", "CVS"),
            "LogisticsSubType": order_data.get("LogisticsSubType", ""),
            "GoodsAmount": order_data.get("GoodsAmount", 0),
            "GoodsName": goods_name,
            "SenderName": order_data.get("SenderName", ""),
            "SenderCellPhone": order_data.get("SenderCellPhone", ""),
            "ReceiverName": receiver_name,
            "ReceiverCellPhone": order_data.get("ReceiverCellPhone", ""),
            "ReceiverStoreID": order_data.get("ReceiverStoreID", ""),
            "ServerReplyURL": order_data.get("ServerReplyURL", ""),
            "IsCollection": order_data.get("IsCollection", "N")
        }
        
        # Only add fields that are actually needed and not empty
        if order_data.get("ReceiverEmail"):
            params["ReceiverEmail"] = order_data.get("ReceiverEmail", "")
        
        # Generate CheckMacValue
        params["CheckMacValue"] = ECPayLogistics.create_check_mac_value(params)
        
        # Send request to ECPay with proper Content-Type
        url = ECPAY_CONFIG[ECPAY_ENV]["create_order"]
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html"
        }
        
        try:
            response = requests.post(url, data=params, headers=headers)
            status_code = response.status_code
            content_type = response.headers.get("content-type", "")
            content = response.text
            
            if status_code != 200:
                return {
                    "error": True, 
                    "message": f"HTTP error: {status_code}", 
                    "details": content
                }
            if params.get("LogisticsSubType") == "FAMIC2C":
                    st.write("Debug - FamilyMart Order Creation:")
                    st.write("URL:", url)
                    st.write("Headers:", headers)
                    st.write("Request Parameters:", params)
                    st.write("Response Status:", status_code)
                    st.write("Response Content-Type:", content_type)
                    st.write("Response Content:", content)

            if status_code != 200:
                return {
                    "error": True, 
                    "message": f"HTTP error: {status_code}", 
                    "details": content
                }
            # Parse response based on content type
            try:
                # HTML response with key-value pairs
                if "text/html" in content_type:
                    result = {}
                    lines = content.strip().split('&')
                    for line in lines:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            result[key] = value
                    
                    # If result is empty but we have content, return it for debugging
                    if not result and content:
                        return {
                            "rawResponse": content,
                            "status": status_code,
                            "contentType": content_type
                        }
                        
                    return result
                    
                # JSON response
                elif "application/json" in content_type:
                    return response.json()
                    
                # Other response types
                else:
                    return {
                        "rawResponse": content,
                        "status": status_code,
                        "contentType": content_type
                    }
                    
            except Exception as e:
                return {
                    "error": True, 
                    "message": f"Failed to parse response: {str(e)}", 
                    "details": content
                }
        except Exception as e:
            return {
                "error": True, 
                "message": f"Request error: {str(e)}"
            }
    @staticmethod
    def query_logistics_order(AllPayLogisticsID=None, MerchantTradeNo=None):
        """
        Query logistics order information from ECPay with enhanced flexibility
        
        Args:
            AllPayLogisticsID (str, optional): ECPay's logistics transaction ID
            MerchantTradeNo (str, optional): Merchant's trade number
        
        Returns:
            dict: Logistics order information
        """
        # Validate input
        if not AllPayLogisticsID and not MerchantTradeNo:
            return {
                "error": True,
                "message": "必須提供 AllPayLogisticsID 或 MerchantTradeNo"
            }
        
        # Determine environment URL
        url = ECPAY_CONFIG[ECPAY_ENV]["query_logistics"]
        
        # Prepare parameters with variations to improve query chances
        variations = []
        
        # If MerchantTradeNo is provided, create variations
        if MerchantTradeNo:
            variations.extend([
                MerchantTradeNo,
                f"SH{MerchantTradeNo}",  # Shopify prefix
                f"SP{MerchantTradeNo}",  # Shopee prefix
                MerchantTradeNo.replace('SH', ''),
                MerchantTradeNo.replace('SP', '')
            ])
        
        # Deduplicate variations
        variations = list(dict.fromkeys(variations))
        
        # Try each variation
        for trade_no in variations:
            # Prepare parameters
            params = {
                "MerchantID": ECPAY_MERCHANT_ID,
                "TimeStamp": int(time.time())  # Current Unix timestamp
            }
            
            # Prefer AllPayLogisticsID if provided
            if AllPayLogisticsID:
                params["AllPayLogisticsID"] = AllPayLogisticsID
            else:
                params["MerchantTradeNo"] = trade_no
            
            # Generate CheckMacValue
            params["CheckMacValue"] = ECPayLogistics.create_check_mac_value(params)
            
            try:
                # Send request
                response = requests.post(
                    url, 
                    data=params, 
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "text/html"
                    }
                )
                
                # Check response
                if response.status_code == 200:
                    # Parse response
                    result = {}
                    lines = response.text.strip().split('&')
                    for line in lines:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            result[key] = value
                    
                    # Check if order was found
                    if result and not result.get('RtnCode') == '0':
                        return result
                
                # If this variation didn't work, continue to next
                continue
            
            except Exception as e:
                # Log the error but continue trying other variations
                print(f"Query error for {trade_no}: {str(e)}")
                continue
        
        # If no variations worked
        return {
            "error": True,
            "message": "找不到對應的物流訂單",
            "details": f"嘗試查詢的編號: {variations}"
        }

    @staticmethod
    def print_shipping_document(logistics_id, payment_no, validation_no=None, document_type="UNIMARTC2C"):
        """Generate shipping document for printing in a new tab"""
        # Prepare parameters
        params = {
            "MerchantID": ECPAY_MERCHANT_ID,
            "AllPayLogisticsID": logistics_id,
            "CVSPaymentNo": payment_no
        }
        
        # Add validation code for 7-ELEVEN
        if document_type == "UNIMARTC2C" and validation_no:
            params["CVSValidationNo"] = validation_no
        
        # Generate CheckMacValue
        params["CheckMacValue"] = ECPayLogistics.create_check_mac_value(params)
        
        # Determine the correct API endpoint
        if document_type == "UNIMARTC2C":
            url = ECPAY_CONFIG[ECPAY_ENV]["print_unimart_c2c"]
        elif document_type == "FAMIC2C":
            url = ECPAY_CONFIG[ECPAY_ENV]["print_fami_c2c"]
        else:
            return {"error": True, "message": "Unsupported document type"}
        
        # Create HTML with auto-submitting form
        form_html = f'''
        <html>
        <body>
            <form id="ecpayForm" method="post" action="{url}" target="_blank">
    '''
        
        # Add hidden inputs for all parameters
        for key, value in params.items():
            form_html += f'    <input type="hidden" name="{key}" value="{value}">\n'
        
        form_html += '''
            </form>
            <script>
                document.getElementById('ecpayForm').submit();
            </script>
        </body>
        </html>
        '''
        
        return form_html
    
    @staticmethod
    def parse_ecpay_response(response_text):
        """Parse ECPay response string into dictionary
        
        Args:
            response_text (str): Response text from ECPay
            
        Returns:
            dict: Parsed response
        """
        result = {}
        for line in response_text.split('&'):
            if '=' in line:
                key, value = line.split('=', 1)
                result[key] = value
        return result


class ECPayDatabase:
    """Database operations for ECPay integration"""
    
    def __init__(self, db_connection):
        """Initialize with database connection
        
        Args:
            db_connection: Database connection object
        """
        self.conn = db_connection
    
    def init_tables(self):
        """Create necessary tables for ECPay integration"""
        try:
            cursor = self.conn.cursor()
            
            # Create ECPay credentials table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ecpay_credentials (
                    id SERIAL PRIMARY KEY,
                    merchant_id VARCHAR(20) NOT NULL,
                    hash_key VARCHAR(50) NOT NULL,
                    hash_iv VARCHAR(50) NOT NULL,
                    environment VARCHAR(10) DEFAULT 'test',
                    sender_name VARCHAR(50),
                    sender_phone VARCHAR(20),
                    sender_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create ECPay logistics orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ecpay_logistics_orders (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL,
                    platform VARCHAR(20) NOT NULL,
                    ecpay_logistics_id VARCHAR(50),
                    logistics_type VARCHAR(20) NOT NULL,
                    logistics_sub_type VARCHAR(20) NOT NULL,
                    store_id VARCHAR(10),
                    cvs_payment_no VARCHAR(20),
                    cvs_validation_no VARCHAR(10),
                    status VARCHAR(20),
                    status_msg TEXT,
                    tracking_number VARCHAR(50),
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(order_id, platform)
                )
            """)
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Database error: {str(e)}")
            return False
    def save_sender_info(self, sender_info):
        """Save only the sender information
        
        Args:
            sender_info (dict): Sender information with name, phone, and address
            
        Returns:
            bool: Success status
        """
        try:
            cursor = self.conn.cursor()
            
            # Check if there's an existing record
            cursor.execute("SELECT id FROM ecpay_credentials LIMIT 1")
            record = cursor.fetchone()
            
            if record:
                # Update existing record
                cursor.execute("""
                    UPDATE ecpay_credentials 
                    SET 
                        sender_name = %s,
                        sender_phone = %s,
                        sender_address = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                """, (
                    sender_info.get("name"),
                    sender_info.get("phone"),
                    sender_info.get("address"),
                    record[0]
                ))
            else:
                # Insert new record with default values for credentials
                cursor.execute("""
                    INSERT INTO ecpay_credentials 
                    (merchant_id, hash_key, hash_iv, environment, sender_name, sender_phone, sender_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    'placeholder',  # Using placeholder since real values will come from secrets
                    'placeholder',
                    'placeholder',
                    'test',
                    sender_info.get("name"),
                    sender_info.get("phone"),
                    sender_info.get("address")
                ))
                
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving sender info: {str(e)}")
            return False
    def save_credentials(self, merchant_id, hash_key, hash_iv, environment="test", sender_info=None):
        """Save ECPay credentials
        
        Args:
            merchant_id (str): ECPay merchant ID
            hash_key (str): ECPay hash key
            hash_iv (str): ECPay hash IV
            environment (str): "test" or "production"
            sender_info (dict, optional): Default sender information
            
        Returns:
            bool: Success status
        """
        try:
            cursor = self.conn.cursor()
            
            sender_name = None
            sender_phone = None
            sender_address = None
            
            if sender_info:
                sender_name = sender_info.get("name")
                sender_phone = sender_info.get("phone")
                sender_address = sender_info.get("address")
            
            cursor.execute("""
                INSERT INTO ecpay_credentials 
                (merchant_id, hash_key, hash_iv, environment, sender_name, sender_phone, sender_address, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    merchant_id = EXCLUDED.merchant_id,
                    hash_key = EXCLUDED.hash_key,
                    hash_iv = EXCLUDED.hash_iv,
                    environment = EXCLUDED.environment,
                    sender_name = EXCLUDED.sender_name,
                    sender_phone = EXCLUDED.sender_phone,
                    sender_address = EXCLUDED.sender_address,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                merchant_id,
                hash_key,
                hash_iv,
                environment,
                sender_name,
                sender_phone,
                sender_address
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving ECPay credentials: {str(e)}")
            return False
    
    def get_credentials(self):
        """Get ECPay credentials
        
        Returns:
            dict: ECPay credentials and sender information
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    merchant_id, hash_key, hash_iv, environment,
                    sender_name, sender_phone, sender_address
                FROM ecpay_credentials
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            
            result = cursor.fetchone()
            if result:
                return {
                    "merchant_id": result[0],
                    "hash_key": result[1],
                    "hash_iv": result[2],
                    "environment": result[3],
                    "sender_name": result[4],
                    "sender_phone": result[5],
                    "sender_address": result[6]
                }
            return None
        except Exception as e:
            print(f"Error getting ECPay credentials: {str(e)}")
            return None
    
    def save_logistics_order(self, order_data):
        """Save ECPay logistics order information
        
        Args:
            order_data (dict): Order information
                - order_id: Original order ID
                - platform: "shopee" or "shopify"
                - ecpay_logistics_id: ECPay logistics ID
                - logistics_type: Logistics type
                - logistics_sub_type: Logistics subtype
                - store_id: Store ID
                - cvs_payment_no: CVS payment number
                - cvs_validation_no: CVS validation number
                - status: Order status
                - status_msg: Status message
                - tracking_number: Tracking number
                
        Returns:
            bool: Success status
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO ecpay_logistics_orders
                (order_id, platform, ecpay_logistics_id, logistics_type, 
                logistics_sub_type, store_id, cvs_payment_no, cvs_validation_no,
                status, status_msg, tracking_number, update_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (order_id, platform) DO UPDATE SET
                    ecpay_logistics_id = EXCLUDED.ecpay_logistics_id,
                    logistics_type = EXCLUDED.logistics_type,
                    logistics_sub_type = EXCLUDED.logistics_sub_type,
                    store_id = EXCLUDED.store_id,
                    cvs_payment_no = EXCLUDED.cvs_payment_no,
                    cvs_validation_no = EXCLUDED.cvs_validation_no,
                    status = EXCLUDED.status,
                    status_msg = EXCLUDED.status_msg,
                    tracking_number = EXCLUDED.tracking_number,
                    update_time = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                order_data.get("order_id"),
                order_data.get("platform"),
                order_data.get("ecpay_logistics_id"),
                order_data.get("logistics_type"),
                order_data.get("logistics_sub_type"),
                order_data.get("store_id"),
                order_data.get("cvs_payment_no"),
                order_data.get("cvs_validation_no"),
                order_data.get("status"),
                order_data.get("status_msg"),
                order_data.get("tracking_number")
            ))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving logistics order: {str(e)}")
            return False
    
    def get_logistics_order(self, order_id, platform):
        """Get ECPay logistics order information
        
        Args:
            order_id (str): Original order ID
            platform (str): "shopee" or "shopify"
            
        Returns:
            dict: Logistics order information
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    order_id, platform, ecpay_logistics_id, logistics_type, 
                    logistics_sub_type, store_id, cvs_payment_no, cvs_validation_no,
                    status, status_msg, tracking_number, create_time, update_time
                FROM ecpay_logistics_orders
                WHERE order_id = %s AND platform = %s
            """, (order_id, platform))
            
            result = cursor.fetchone()
            if result:
                column_names = [
                    "order_id", "platform", "ecpay_logistics_id", "logistics_type",
                    "logistics_sub_type", "store_id", "cvs_payment_no", "cvs_validation_no",
                    "status", "status_msg", "tracking_number", "create_time", "update_time"
                ]
                return dict(zip(column_names, result))
            return None
        except Exception as e:
            print(f"Error getting logistics order: {str(e)}")
            return None