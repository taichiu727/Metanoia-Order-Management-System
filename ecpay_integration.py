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
        "print_fami_c2c": "https://logistics-stage.ecpay.com.tw/Express/PrintFAMIC2COrderInfo"
    },
    "production": {
        "create_order": "https://logistics.ecpay.com.tw/Express/Create",
        "print_unimart_c2c": "https://logistics.ecpay.com.tw/Express/PrintUniMartC2COrderInfo",
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
        """Generate CheckMacValue for ECPay API"""
        if not ECPAY_HASH_KEY or not ECPAY_HASH_IV:
            raise ValueError("ECPay credentials not set. Call set_ecpay_credentials() first.")
            
        # Step 1: Sort parameters alphabetically
        sorted_params = sorted(params.items())
        
        # Step 2: Create URL encoded string
        encoding_str = "HashKey=" + ECPAY_HASH_KEY
        for key, value in sorted_params:
            encoding_str += "&" + key + "=" + str(value)
        encoding_str += "&HashIV=" + ECPAY_HASH_IV
        
        # Step 3: URL encode the string
        encoding_str = quote(encoding_str, safe="/").lower()
        
        # Step 4: MD5 hash and convert to uppercase
        check_mac_value = hashlib.md5(encoding_str.encode("utf-8")).hexdigest().upper()
        
        return check_mac_value
    
    @staticmethod
    def create_logistics_order(order_data):
        """Create a new logistics order with ECPay"""
        # Prepare API parameters
        params = {
            "MerchantID": ECPAY_MERCHANT_ID,
            # Add all required fields, ensuring proper formatting
            "MerchantTradeNo": order_data.get("MerchantTradeNo", "") + str(int(time.time()))[-5:],  # Add timestamp suffix to ensure uniqueness
            "MerchantTradeDate": order_data.get("MerchantTradeDate", ""),
            "LogisticsType": order_data.get("LogisticsType", "CVS"),
            "LogisticsSubType": order_data.get("LogisticsSubType", ""),
            "GoodsAmount": order_data.get("GoodsAmount", 0),
            "GoodsName": order_data.get("GoodsName", ""),
            "SenderName": order_data.get("SenderName", ""),
            "SenderCellPhone": order_data.get("SenderCellPhone", ""),
            "ReceiverName": order_data.get("ReceiverName", ""),
            "ReceiverCellPhone": order_data.get("ReceiverCellPhone", ""),
            "ReceiverEmail": order_data.get("ReceiverEmail", ""),
            "ReceiverStoreID": order_data.get("ReceiverStoreID", ""),
            "ServerReplyURL": order_data.get("ServerReplyURL", ""),
            "IsCollection": order_data.get("IsCollection", "N")
        }
        
        # Print raw parameters for debugging
        print("Request Parameters:")
        for key, value in params.items():
            print(f"{key}: {value}")
        
        # Generate CheckMacValue
        params["CheckMacValue"] = ECPayLogistics.create_check_mac_value(params)
        
        # Send request to ECPay
        url = ECPAY_CONFIG[ECPAY_ENV]["create_order"]
        print(f"Sending request to: {url}")
        
        try:
            response = requests.post(url, data=params)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Content-Type: {response.headers.get('content-type', '')}")
            print(f"Response Content: {response.text}")
            
            if response.status_code != 200:
                return {
                    "error": True, 
                    "message": f"HTTP error: {response.status_code}", 
                    "details": response.text
                }
            
            # Parse response
            try:
                # First try to parse as JSON
                if response.text.strip().startswith('{'):
                    return response.json()
                
                # Otherwise parse the key=value format
                result = {}
                for line in response.text.split('&'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        result[key] = value
                
                # If result is empty, return the raw response
                if not result:
                    return {
                        "rawResponse": response.text,
                        "status": response.status_code
                    }
                    
                return result
            except Exception as e:
                return {
                    "error": True, 
                    "message": f"Failed to parse response: {str(e)}", 
                    "details": response.text
                }
        except Exception as e:
            return {
                "error": True, 
                "message": f"Request error: {str(e)}"
            }
    
    @staticmethod
    def print_shipping_document(logistics_id, payment_no, validation_no=None, document_type="UNIMARTC2C"):
        """Generate shipping document for printing
        
        Args:
            logistics_id (str): ECPay logistics transaction ID
            payment_no (str): Shipping number
            validation_no (str, optional): Validation code (required for 7-ELEVEN)
            document_type (str): "UNIMARTC2C" for 7-ELEVEN or "FAMIC2C" for FamilyMart
            
        Returns:
            str: HTML content for printing or error message
        """
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
        
        # Create a form to submit via JavaScript
        form_html = f"""
        <html>
        <body>
        <form id="ecpayForm" method="post" action="{url}" target="_blank">
        """
        
        for key, value in params.items():
            form_html += f'<input type="hidden" name="{key}" value="{value}">\n'
        
        form_html += """
        </form>
        <script>
            document.getElementById('ecpayForm').submit();
        </script>
        </body>
        </html>
        """
        
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