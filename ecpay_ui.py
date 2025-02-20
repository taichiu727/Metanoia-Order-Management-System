import streamlit as st
import time
from datetime import datetime
import json
from ecpay_integration import ECPayLogistics, ECPAY_ENV, set_ecpay_credentials

def settings_ui(db):
    """ECPay settings UI component
    
    Args:
        db: Database connection object
    """
    st.subheader("ECPay 綠界科技設定")
    
    # Try to load existing credentials
    ecpay_db = db.get_credentials()
    if ecpay_db:
        st.success("✅ ECPay 已連接")
        st.info(f"商店代號: {ecpay_db['merchant_id']} (環境: {'測試' if ecpay_db['environment'] == 'test' else '正式'})")
        
        # Load credentials to global variables
        set_ecpay_credentials(
            ecpay_db['merchant_id'],
            ecpay_db['hash_key'],
            ecpay_db['hash_iv'],
            ecpay_db['environment']
        )
    
    # Declare variables outside the form so they're accessible later
    merchant_id = ""
    hash_key = ""
    hash_iv = ""
    environment = "test"
    sender_name = ""
    sender_phone = ""
    sender_address = ""
    
    # Settings form
    with st.form("ecpay_settings"):
        col1, col2 = st.columns(2)
        
        with col1:
            merchant_id = st.text_input(
                "商店代號 (MerchantID)", 
                value=ecpay_db['merchant_id'] if ecpay_db else "",
                help="綠界科技提供的特店編號"
            )
            hash_key = st.text_input(
                "HashKey", 
                value=ecpay_db['hash_key'] if ecpay_db else "",
                type="password",
                help="綠界科技提供的 HashKey"
            )
            hash_iv = st.text_input(
                "HashIV", 
                value=ecpay_db['hash_iv'] if ecpay_db else "",
                type="password",
                help="綠界科技提供的 HashIV"
            )
            environment = st.selectbox(
                "環境",
                options=["test", "production"],
                index=0 if not ecpay_db or ecpay_db['environment'] == 'test' else 1,
                format_func=lambda x: "測試環境" if x == "test" else "正式環境"
            )
        
        with col2:
            st.subheader("預設寄件人資訊")
            sender_name = st.text_input(
                "寄件人姓名",
                value=ecpay_db['sender_name'] if ecpay_db and ecpay_db['sender_name'] else "",
                help="4-10個字元，不可有數字或特殊符號"
            )
            sender_phone = st.text_input(
                "寄件人手機",
                value=ecpay_db['sender_phone'] if ecpay_db and ecpay_db['sender_phone'] else "",
                help="手機號碼格式，例如: 0912345678"
            )
            sender_address = st.text_area(
                "寄件人地址",
                value=ecpay_db['sender_address'] if ecpay_db and ecpay_db['sender_address'] else "",
                height=100
            )
        
        st.write("---")
        submit = st.form_submit_button("儲存設定", use_container_width=True)
    
    # Handle form submission outside the form
    if submit:
        # Validate inputs
        if not merchant_id or not hash_key or not hash_iv:
            st.error("請填寫所有必要欄位")
            return
        
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
        
        # Save to database
        success = db.save_credentials(
            merchant_id=merchant_id,
            hash_key=hash_key, 
            hash_iv=hash_iv,
            environment=environment,
            sender_info={
                "name": sender_name,
                "phone": sender_phone,
                "address": sender_address
            }
        )
        
        if success:
            # Update global variables
            set_ecpay_credentials(merchant_id, hash_key, hash_iv, environment)
            st.success("設定已儲存！")
            st.rerun()
        else:
            st.error("儲存設定時發生錯誤")
    
    # Separate test connection functionality
    if ecpay_db:
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
                    "SenderName": ecpay_db.get('sender_name') or "測試寄件人",
                    "SenderCellPhone": ecpay_db.get('sender_phone') or "0912345678",
                    "ReceiverName": "測試收件人",
                    "ReceiverCellPhone": "0987654321",
                    "ReceiverStoreID": "131386",  # 測試門市
                    "ServerReplyURL": "https://example.com/callback"
                }
                
                # Set credentials
                set_ecpay_credentials(
                    ecpay_db['merchant_id'],
                    ecpay_db['hash_key'],
                    ecpay_db['hash_iv'],
                    ecpay_db['environment']
                )
                
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
                # Load ECPay credentials
                ecpay_creds = db.get_credentials()
                if not ecpay_creds:
                    st.error("請先設定綠界科技帳號")
                    return
                
                # Set credentials
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


def shopify_ecpay_ui(order, db):
    """ECPay logistics UI for Shopify orders
    
    Args:
        order (dict): Shopify order data
        db: Database connection
    """
    logistics_options = {
        "UNIMARTC2C": "7-ELEVEN 超商交貨便",
        "FAMIC2C": "全家店到店",
        "HILIFEC2C": "萊爾富店到店",
        "OKMARTC2C": "OK超商店到店"
    }
    
    with st.expander("綠界物流設定"):
        # Get customer info
        customer_name = f"{order.get('customer', {}).get('first_name', '')} {order.get('customer', {}).get('last_name', '')}".strip()
        
        # Get shipping address and phone
        shipping_address = order.get('shipping_address', {})
        phone = shipping_address.get('phone', '')
        
        # Calculate order total
        total_amount = int(float(order.get('total_price', '0')))
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("收件人資訊")
            receiver_name = st.text_input("收件人姓名", value=customer_name, key=f"name_{order['order_number']}")
            receiver_phone = st.text_input("收件人電話", value=phone, key=f"phone_{order['order_number']}")
            receiver_email = st.text_input("收件人 Email", value=order.get('email', ''), key=f"email_{order['order_number']}")
        
        with col2:
            st.subheader("物流設定")
            selected_logistics = st.selectbox(
                "物流類型",
                options=list(logistics_options.keys()),
                format_func=lambda x: logistics_options[x],
                key=f"logistics_{order['order_number']}"
            )
            
            store_id = st.text_input("門市代號", key=f"store_{order['order_number']}")
            
            goods_amount = st.number_input(
                "商品金額",
                min_value=1, 
                max_value=20000,
                value=total_amount,
                key=f"amount_{order['order_number']}"
            )
            
            is_collection = st.checkbox(
                "代收貨款",
                value=False,
                key=f"collection_{order['order_number']}"
            )
        
        # Prepare goods description
        items_desc = ", ".join([f"{item['title']} x {item['quantity']}" for item in order.get('line_items', [])][:3])
        if len(order.get('line_items', [])) > 3:
            items_desc += f" 等{len(order.get('line_items', []))}項商品"
            
        # Trim to maximum allowed length (50 characters)
        if len(items_desc) > 47:
            items_desc = items_desc[:47] + "..."
            
        goods_name = st.text_input(
            "商品描述",
            value=items_desc,
            max_chars=50,
            key=f"goods_{order['order_number']}"
        )
        
        # Get domain for callback URL
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