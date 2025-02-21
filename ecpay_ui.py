import streamlit as st
import time
from datetime import datetime
import json
from ecpay_integration import ECPayLogistics, ECPAY_ENV, set_ecpay_credentials

def settings_ui(db):
    """ECPay settings UI component with Streamlit secrets support
    
    Args:
        db: Database connection object
    """
    st.subheader("ECPay 綠界科技設定")
    
    # Load credentials from Streamlit secrets
    merchant_id = st.secrets.get("ECPAY_MERCHANT_ID")
    hash_key = st.secrets.get("ECPAY_HASH_KEY")
    hash_iv = st.secrets.get("ECPAY_HASH_IV")
    
    # Initial state for sender info and environment
    sender_name = ""
    sender_phone = ""
    sender_address = ""
    environment = "test"
    
    # Try to load existing sender info from database
    ecpay_db = db.get_credentials()
    if ecpay_db:
        sender_name = ecpay_db.get('sender_name', '')
        sender_phone = ecpay_db.get('sender_phone', '')
        sender_address = ecpay_db.get('sender_address', '')
    
    # Display connection status
    if merchant_id and hash_key and hash_iv:
        st.success("✅ ECPay 憑證已載入")
        st.info(f"商店代號: {merchant_id} (環境: {'測試' if environment == 'test' else '正式'})")
        #22
        # Set credentials globally
        set_ecpay_credentials(merchant_id, hash_key, hash_iv, environment)
    else:
        st.error("未找到 ECPay 憑證，請檢查 Streamlit 密鑰設定")
    
    # Settings form
    with st.form("ecpay_settings"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### 系統憑證 (自 Streamlit Secrets)")
            st.text_input(
                "商店代號 (MerchantID)", 
                value=merchant_id or "",
                disabled=True,
                help="從 Streamlit Secrets 載入，無法直接編輯"
            )
            st.text_input(
                "HashKey", 
                value="*" * len(hash_key) if hash_key else "",
                type="password",
                disabled=True,
                help="從 Streamlit Secrets 載入，無法直接編輯"
            )
            st.text_input(
                "HashIV", 
                value="*" * len(hash_iv) if hash_iv else "",
                type="password",
                disabled=True,
                help="從 Streamlit Secrets 載入，無法直接編輯"
            )
            
            # Hidden environment selection since using secrets
            st.selectbox(
                "環境",
                options=["test", "production"],
                index=0,
                format_func=lambda x: "測試環境" if x == "test" else "正式環境",
                disabled=True
            )
        
        with col2:
            st.subheader("預設寄件人資訊")
            sender_name = st.text_input(
                "寄件人姓名",
                value=sender_name,
                help="4-10個字元，不可有數字或特殊符號"
            )
            sender_phone = st.text_input(
                "寄件人手機",
                value=sender_phone,
                help="手機號碼格式，例如: 0912345678"
            )
            sender_address = st.text_area(
                "寄件人地址",
                value=sender_address,
                height=100
            )
        
        st.write("---")
        submit = st.form_submit_button("儲存設定", use_container_width=True)
    
    # Handle form submission
    if submit:
        # Validate sender name (4-10 characters, no numbers or special chars)
        if sender_name:
            if len(sender_name) < 2 or len(sender_name) > 10:
                st.error("寄件人姓名需要2-10個字")
                return
                
            if any(char.isdigit() for char in sender_name):
                st.error("寄件人姓名不可包含數字")
                return
            
            # Simple regex for special characters
            if not all(('\u4e00' <= char <= '\u9fff') or char.isalpha() or char.isspace() for char in sender_name):
                st.error("寄件人姓名不可包含特殊符號")
                return
        
        # Validate phone (must be 10 digits starting with 09)
        if sender_phone and (len(sender_phone) != 10 or not sender_phone.startswith("09") or not sender_phone.isdigit()):
            st.error("寄件人手機必須是10位數字且以09開頭")
            return
        
        # Save sender info to database
        success = db.save_sender_info({
            "name": sender_name,
            "phone": sender_phone,
            "address": sender_address
        })
        
        if success:
            st.success("寄件人資訊已儲存！")
        else:
            st.error("儲存設定時發生錯誤")
    
    # Separate test connection functionality
    if merchant_id and hash_key and hash_iv:
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col2:
            test_conn = st.button("測試連線", use_container_width=True, key="test_ecpay_conn")
        
        if test_conn:
            try:
                # Prepare test order data
                test_order = {
                    "MerchantTradeNo": f"TEST{int(time.time())}",
                    "MerchantTradeDate": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                    "LogisticsType": "CVS",
                    "LogisticsSubType": "UNIMARTC2C",  # 7-ELEVEN C2C
                    "GoodsAmount": 100,
                    "GoodsName": "測試商品",
                    "SenderName": sender_name or "測試寄件人",
                    "SenderCellPhone": sender_phone or "0912345678",
                    "ReceiverName": "測試收件人",
                    "ReceiverCellPhone": "0987654321",
                    "ReceiverStoreID": "131386",  # 測試門市
                    "ServerReplyURL": "https://example.com/callback"
                }
                
                # Set credentials
                set_ecpay_credentials(merchant_id, hash_key, hash_iv, "test")
                
                # Test API connection
                st.info("正在測試連線...")
                response = ECPayLogistics.create_logistics_order(test_order)
                
                if "RtnCode" in response and response["RtnCode"] == "1":
                    st.success("連線成功！")
                    st.json(response)
                else:
                    st.error("測試連線失敗")
                    st.json(response)
            except Exception as e:
                st.error(f"測試連線時發生錯誤: {str(e)}")


def render_ecpay_button(order_id, platform, customer_data, logistics_data, db):
    """Render ECPay logistics button
    
    Args:
        order_id (str): Order ID
        platform (str): "shopee" or "shopify"
        customer_data (dict): Customer information
        logistics_data (dict): Logistics preferences
        db: Database connection
    """
    # Check if order already has ECPay logistics
    existing_order = db.get_logistics_order(order_id, platform)
    
    if existing_order and existing_order.get('ecpay_logistics_id'):
        # Order already has ECPay logistics, show status and options
        st.success(f"已建立綠界物流單 (ID: {existing_order['ecpay_logistics_id']})")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("列印託運單", key=f"print_{order_id}"):
                logistics_id = existing_order['ecpay_logistics_id']
                payment_no = existing_order['cvs_payment_no']
                validation_no = existing_order.get('cvs_validation_no')
                logistics_subtype = existing_order['logistics_sub_type']
                
                document_type = "UNIMARTC2C" if "UNIMART" in logistics_subtype else "FAMIC2C"
                
                form_html = ECPayLogistics.print_shipping_document(
                    logistics_id=logistics_id,
                    payment_no=payment_no,
                    validation_no=validation_no,
                    document_type=document_type
                )
                
                # Display the form for auto-submission
                st.components.v1.html(form_html, height=0)
                st.success("託運單開啟中，請稍候...")
                
        with col2:
            if st.button("查詢物流狀態", key=f"status_{order_id}"):
                st.info(f"物流狀態: {existing_order.get('status_msg', '未知')}")
                if existing_order.get('tracking_number'):
                    st.info(f"追蹤號碼: {existing_order['tracking_number']}")
    else:
        # Order doesn't have ECPay logistics yet, show create button
        if st.button("建立綠界物流單", key=f"create_ecpay_{order_id}"):
            try:
                # Try to load credentials from database first
                ecpay_creds = db.get_credentials()
                
                # If not in database, use Streamlit secrets
                if not ecpay_creds or not ecpay_creds.get('merchant_id'):
                    merchant_id = st.secrets.get("ECPAY_MERCHANT_ID")
                    hash_key = st.secrets.get("ECPAY_HASH_KEY") 
                    hash_iv = st.secrets.get("ECPAY_HASH_IV")
                    
                    if not (merchant_id and hash_key and hash_iv):
                        st.error("未找到 ECPay 憑證，請在 Streamlit Secrets 或資料庫中設定")
                        return
                        
                    # Get sender info from database
                    sender_info = {}
                    if ecpay_creds:
                        sender_info = {
                            'sender_name': ecpay_creds.get('sender_name', ''),
                            'sender_phone': ecpay_creds.get('sender_phone', ''),
                            'sender_address': ecpay_creds.get('sender_address', '')
                        }
                    
                    # Use the secrets and sender info
                    set_ecpay_credentials(merchant_id, hash_key, hash_iv, "test")
                else:
                    # Use database credentials
                    set_ecpay_credentials(
                        ecpay_creds['merchant_id'],
                        ecpay_creds['hash_key'],
                        ecpay_creds['hash_iv'],
                        ecpay_creds['environment']
                    )
                
                # Format current time for ECPay
                current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                
                # Prepare order data for ECPay
                order_request = {
                    "MerchantTradeNo": f"{platform[:2].upper()}{order_id}",
                    "MerchantTradeDate": current_time,
                    "LogisticsType": "CVS",
                    "LogisticsSubType": logistics_data.get('logistics_subtype', 'UNIMARTC2C'),
                    "GoodsAmount": logistics_data.get('amount', 0),
                    "GoodsName": logistics_data.get('goods_name', '商品'),
                    "SenderName": ecpay_creds.get('sender_name', ''),
                    "SenderCellPhone": ecpay_creds.get('sender_phone', ''),
                    "ReceiverName": customer_data.get('name', ''),
                    "ReceiverCellPhone": customer_data.get('phone', ''),
                    "ReceiverEmail": customer_data.get('email', ''),
                    "ReceiverStoreID": logistics_data.get('store_id', ''),
                    "ServerReplyURL": logistics_data.get('callback_url', ""),
                    "IsCollection": logistics_data.get('is_collection', 'N')
                }
                
                # Create logistics order
                with st.spinner("建立物流單中..."):
                    response = ECPayLogistics.create_logistics_order(order_request)
                    
                    if "RtnCode" in response and response["RtnCode"] == "1":
                        # Success - store the logistics order information
                        logistics_data = {
                            "order_id": order_id,
                            "platform": platform,
                            "ecpay_logistics_id": response.get("AllPayLogisticsID", ""),
                            "logistics_type": "CVS",
                            "logistics_sub_type": logistics_data.get('logistics_subtype', 'UNIMARTC2C'),
                            "store_id": logistics_data.get('store_id', ''),
                            "cvs_payment_no": response.get("CVSPaymentNo", ""),
                            "cvs_validation_no": response.get("CVSValidationNo", ""),
                            "status": response.get("RtnCode", ""),
                            "status_msg": response.get("RtnMsg", ""),
                            "tracking_number": ""
                        }
                        
                        # Save to database
                        db.save_logistics_order(logistics_data)
                        
                        st.success(f"綠界物流單建立成功！ID: {response.get('AllPayLogisticsID', '')}")
                        if "CVSPaymentNo" in response:
                            st.info(f"寄貨編號: {response['CVSPaymentNo']}")
                        if "CVSValidationNo" in response:
                            st.info(f"驗證碼: {response['CVSValidationNo']}")
                            
                        # Show print button
                        if st.button("列印託運單", key=f"print_new_{order_id}"):
                            logistics_id = response.get("AllPayLogisticsID", "")
                            payment_no = response.get("CVSPaymentNo", "")
                            validation_no = response.get("CVSValidationNo", "")
                            doc_type = "UNIMARTC2C" if "UNIMART" in logistics_data.get('logistics_subtype', '') else "FAMIC2C"
                            
                            form_html = ECPayLogistics.print_shipping_document(
                                logistics_id=logistics_id,
                                payment_no=payment_no,
                                validation_no=validation_no,
                                document_type=doc_type
                            )
                            
                            st.components.v1.html(form_html, height=0)
                            st.success("託運單開啟中，請稍候...")
                        
                        # Rerun to refresh the UI
                        st.rerun()
                    else:
                        # Error
                        st.error(f"建立物流單失敗: {response.get('RtnMsg', '未知錯誤')}")
                        st.json(response)
            except Exception as e:
                st.error(f"建立物流單時發生錯誤: {str(e)}")

@st.fragment
def shopify_ecpay_ui(order, db):
    """Simple ECPay logistics UI for Shopify orders
    
    Args:
        order (dict): Shopify order data
        db: Database connection
    """
    # Logistics options
    logistics_options = {
        "UNIMARTC2C": "7-ELEVEN 超商交貨便",
        "FAMIC2C": "全家店到店",
        "HILIFEC2C": "萊爾富店到店",
        "OKMARTC2C": "OK超商店到店"
    }
    
    # Helper function to extract attribute
    def get_note_attribute(attributes, key_patterns):
        for attr in attributes:
            attr_name = attr.get('name', '').lower()
            for pattern in key_patterns:
                if pattern in attr_name:
                    return str(attr.get('value', '')).strip()
        return ''
    
    # Prepare customer and order information
    customer = order.get('customer', {})
    shipping_address = order.get('shipping_address', {})
    note_attributes = order.get('note_attributes', [])
    
    # Compile customer name
    customer_name = (
        f"{customer.get('first_name', '')} {customer.get('last_name', '')}"
    ).strip()
    
    # Extract logistics details
    selected_logistics = get_note_attribute(
        note_attributes, 
        ['物流子代碼', 'logisticssubtype', 'logistics_subtype']
    ) or "UNIMARTC2C"
    
    # Extract store ID
    store_id = get_note_attribute(
        note_attributes, 
        ['門市代號', 'cvsstoreid', 'store_id']
    ) or ''
    
    # Compute total amount
    total_amount = int(float(order.get('total_price', '0')))
    
    # Prepare goods description
    line_items = order.get('line_items', [])
    items_desc = ", ".join([f"{item['title']} x {item['quantity']}" for item in line_items[:3]])
    if len(line_items) > 3:
        items_desc += f" 等{len(line_items)}項商品"
    
    # Trim description
    items_desc = (items_desc[:47] + "...") if len(items_desc) > 47 else items_desc
    
    # UI Layout
    with st.container():
        st.header(f"訂單 #{order['order_number']} 物流資訊")
        
        # Receiver Information
        st.subheader("收件人資訊")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("**收件人姓名**")
            receiver_name = st.text_input(
                "姓名", 
                value=customer_name, 
                label_visibility="collapsed",
                key=f"name_{order['order_number']}"
            )
        
        with col2:
            st.write("**收件人電話**")
            receiver_phone = st.text_input(
                "電話", 
                value=shipping_address.get('phone', ''), 
                label_visibility="collapsed",
                key=f"phone_{order['order_number']}"
            )
        
        with col3:
            st.write("**收件人 Email**")
            receiver_email = st.text_input(
                "Email", 
                value=order.get('email', ''), 
                label_visibility="collapsed",
                key=f"email_{order['order_number']}"
            )
        
        # Logistics Information
        st.subheader("物流設定")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("**物流類型**")
            selected_logistics = st.selectbox(
                "物流類型",
                options=list(logistics_options.keys()),
                index=list(logistics_options.keys()).index(selected_logistics),
                format_func=lambda x: logistics_options[x],
                label_visibility="collapsed",
                key=f"logistics_{order['order_number']}"
            )
        
        with col2:
            st.write("**門市代號**")
            store_id = st.text_input(
                "門市代號", 
                value=store_id, 
                label_visibility="collapsed",
                key=f"store_{order['order_number']}"
            )
        
        with col3:
            st.write("**商品金額**")
            goods_amount = st.number_input(
                "商品金額",
                min_value=1, 
                max_value=20000,
                value=total_amount,
                label_visibility="collapsed",
                key=f"amount_{order['order_number']}"
            )
        
        # Additional Options
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**商品描述**")
            goods_name = st.text_input(
                "商品描述",
                value=items_desc,
                max_chars=50,
                label_visibility="collapsed",
                key=f"goods_{order['order_number']}"
            )
        
        with col2:
            st.write("**代收貨款**")
            is_collection = st.checkbox(
                "代收貨款",
                value=False,
                key=f"collection_{order['order_number']}"
            )
        
        # Prepare callback URL
        shopify_domain = order.get('shopify_domain', 'your-store.myshopify.com')
        callback_url = f"https://{shopify_domain}/admin/apps/ecpay-logistics/webhook"
        
        # Prepare logistics data
        logistics_data = {
            'logistics_subtype': selected_logistics,
            'amount': goods_amount,
            'goods_name': goods_name,
            'store_id': store_id,
            'callback_url': callback_url,
            'is_collection': 'Y' if is_collection else 'N'
        }
        
        # Prepare customer data
        customer_data = {
            'name': receiver_name,
            'phone': receiver_phone,
            'email': receiver_email
        }
        
        # Render ECPay button
        st.write("---")
        render_ecpay_button(
            order_id=str(order['order_number']),
            platform="shopify",
            customer_data=customer_data,
            logistics_data=logistics_data,
            db=db
        )


def shopee_ecpay_ui(order, db):
    """ECPay logistics UI for Shopee orders
    
    Args:
        order (dict): Shopee order data
        db: Database connection
    """
    logistics_options = {
        "UNIMARTC2C": "7-ELEVEN 超商交貨便",
        "FAMIC2C": "全家店到店",
        "HILIFEC2C": "萊爾富店到店",
        "OKMARTC2C": "OK超商店到店"
    }
    
    with st.expander("綠界物流設定"):
        # Get basic order info
        order_sn = order["order_sn"]
        
        # Extract receiver info and items
        receiver_name = order.get("recipient_address", {}).get("name", "")
        receiver_phone = order.get("recipient_address", {}).get("phone", "")
        
        # Calculate order total
        total_amount = int(float(order.get("total_amount", 0)) / 100000)  # Convert Shopee amount format
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("收件人資訊")
            receiver_name = st.text_input("收件人姓名", value=receiver_name, key=f"name_{order_sn}")
            receiver_phone = st.text_input("收件人電話", value=receiver_phone, key=f"phone_{order_sn}")
            receiver_email = st.text_input("收件人 Email", key=f"email_{order_sn}")
        
        with col2:
            st.subheader("物流設定")
            selected_logistics = st.selectbox(
                "物流類型",
                options=list(logistics_options.keys()),
                format_func=lambda x: logistics_options[x],
                key=f"logistics_{order_sn}"
            )
            
            store_id = st.text_input("門市代號", key=f"store_{order_sn}")
            
            goods_amount = st.number_input(
                "商品金額",
                min_value=1, 
                max_value=20000,
                value=total_amount,
                key=f"amount_{order_sn}"
            )
            
            is_collection = st.checkbox(
                "代收貨款",
                value=False,
                key=f"collection_{order_sn}"
            )
        
        # Prepare goods description
        items = []
        for item in order.get("item_list", []):
            items.append(f"{item['item_name']} x {item['model_quantity_purchased']}")
        
        items_desc = ", ".join(items[:3])
        if len(items) > 3:
            items_desc += f" 等{len(items)}項商品"
            
        # Trim to maximum allowed length
        if len(items_desc) > 47:
            items_desc = items_desc[:47] + "..."
            
        goods_name = st.text_input(
            "商品描述",
            value=items_desc,
            max_chars=50,
            key=f"goods_{order_sn}"
        )
        
        # Callback URL for Shopee
        callback_url = "https://your-app-domain.com/api/ecpay-webhook"
        
        # Prepare logistics data
        logistics_data = {
            'logistics_subtype': selected_logistics,
            'amount': goods_amount,
            'goods_name': goods_name,
            'store_id': store_id,
            'callback_url': callback_url,
            'is_collection': 'Y' if is_collection else 'N'
        }
        
        # Prepare customer data
        customer_data = {
            'name': receiver_name,
            'phone': receiver_phone,
            'email': receiver_email
        }
        
        # Render ECPay button
        render_ecpay_button(
            order_id=order_sn,
            platform="shopee",
            customer_data=customer_data,
            logistics_data=logistics_data,
            db=db
        )


def init_ecpay_session():
    """Initialize ECPay-related session state variables"""
    if 'ecpay_initialized' not in st.session_state:
        st.session_state.ecpay_initialized = True
        
        # ECPay-specific session state variables
        if 'ecpay_logistics_history' not in st.session_state:
            st.session_state.ecpay_logistics_history = {}