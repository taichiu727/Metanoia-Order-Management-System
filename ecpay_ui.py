import streamlit as st
import time
from datetime import datetime
import json
from ecpay_integration import ECPayLogistics, ECPAY_ENV, set_ecpay_credentials

def settings_ui(db):
    """ECPay settings UI component with fixed sender information"""
    st.subheader("ECPay 綠界科技設定")
    
    # Display fixed sender information
    st.success("✅ 寄件人資訊已設定")
    st.info("寄件人: 邱泰滕")
    st.info("聯絡電話: 0988528467")
    
    # Load credentials from Streamlit secrets
    merchant_id = st.secrets.get("ECPAY_MERCHANT_ID")
    hash_key = st.secrets.get("ECPAY_HASH_KEY")
    hash_iv = st.secrets.get("ECPAY_HASH_IV")
    
    # Display connection status
    if merchant_id and hash_key and hash_iv:
        st.success("✅ ECPay 憑證已載入")
        st.info(f"商店代號: {merchant_id} (環境: 正式)")
        
        # Set credentials globally for production
        set_ecpay_credentials(merchant_id, hash_key, hash_iv, "production")
        
        # Test connection button
        if st.button("測試連線", key="test_ecpay_conn"):
            try:
                # Prepare test order data
                test_order = {
                    "MerchantTradeNo": f"TEST{int(time.time())}",
                    "MerchantTradeDate": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                    "LogisticsType": "CVS",
                    "LogisticsSubType": "UNIMARTC2C",  # 7-ELEVEN C2C
                    "GoodsAmount": 100,
                    "GoodsName": "測試商品",
                    "SenderName": "邱泰滕",
                    "SenderCellPhone": "0988528467",
                    "ReceiverName": "測試收件人",
                    "ReceiverCellPhone": "0987654321",
                    "ReceiverStoreID": "131386",  # Using test store ID
                    "ServerReplyURL": "https://example.com/callback"
                }
                
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
    else:
        st.error("未找到 ECPay 憑證，請檢查 Streamlit 密鑰設定")


def truncate_goods_name(goods_name):
    """
    Truncate goods name to maximum 25 characters
    
    Args:
        goods_name (str): Original goods name
    
    Returns:
        str: Truncated goods name
    """
    # Remove any special characters
    import re
    cleaned_name = re.sub(r'[^\w\s\u4e00-\u9fff,.]', '', goods_name)
    
    # Truncate to 25 characters
    if len(cleaned_name) > 25:
        return cleaned_name[:22] + "..."
    
    return cleaned_name

def truncate_goods_name(goods_name):
    """
    Truncate goods name to maximum 25 characters
    
    Args:
        goods_name (str): Original goods name
    
    Returns:
        str: Truncated goods name
    """
    # Remove any special characters
    import re
    cleaned_name = re.sub(r'[^\w\s\u4e00-\u9fff,.]', '', goods_name)
    
    # Truncate to 25 characters
    if len(cleaned_name) > 25:
        return cleaned_name[:22] + "..."
    
    return cleaned_name

def render_ecpay_button(order_id, platform, customer_data, logistics_data, db):
    """Render ECPay logistics button with merchant trade number debugging
    
    Args:
        order_id (str): Order ID
        platform (str): "shopee" or "shopify"
        customer_data (dict): Customer information
        logistics_data (dict): Logistics preferences
        db: Database connection
    """
    # Columns for layout
    col1, col2 = st.columns(2)
    
    with col1:
        # Always show create logistics order button
        if st.button("建立綠界物流單", key=f"create_ecpay_{order_id}"):
            try:
                # Use Streamlit secrets for credentials
                merchant_id = st.secrets.get("ECPAY_MERCHANT_ID")
                hash_key = st.secrets.get("ECPAY_HASH_KEY") 
                hash_iv = st.secrets.get("ECPAY_HASH_IV")
                
                if not (merchant_id and hash_key and hash_iv):
                    st.error("未找到 ECPay 憑證，請在 Streamlit Secrets 中設定")
                    return
                    
                # Set credentials for production environment
                set_ecpay_credentials(merchant_id, hash_key, hash_iv, "production")
                
                # Format current time for ECPay
                current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                
                # Clean up receiver name if needed
                receiver_name = customer_data.get('name', '')
                if receiver_name and len(receiver_name) > 10:  # Limit to max 10 chars
                    receiver_name = receiver_name[:10]
                
                # Truncate goods name to 25 characters
                goods_name = truncate_goods_name(logistics_data.get('goods_name', '商品'))
                
                # Use Shopify order number EXACTLY as #1213
                merchant_trade_no = f"#{order_id}"
                
                # Detailed logging of merchant trade number
                st.write(f"Debug: Merchant Trade Number: {merchant_trade_no}")
                st.write(f"Debug: Order ID: {order_id}")
                st.write(f"Debug: Platform: {platform}")
                
                order_request = {
                    "MerchantTradeNo": merchant_trade_no,
                    "MerchantTradeDate": current_time,
                    "LogisticsType": "CVS",
                    "LogisticsSubType": logistics_data.get('logistics_subtype', 'UNIMARTC2C'),
                    "GoodsAmount": logistics_data.get('amount', 0),
                    "GoodsName": goods_name,
                    "SenderName": "邱泰滕",
                    "SenderCellPhone": "0988528467",
                    "ReceiverName": receiver_name,
                    "ReceiverCellPhone": customer_data.get('phone', ''),
                    "ReceiverEmail": customer_data.get('email', ''),
                    "ReceiverStoreID": logistics_data.get('store_id', ''),
                    "ServerReplyURL": logistics_data.get('callback_url', ""),
                    "IsCollection": logistics_data.get('is_collection', 'N')
                }
                
                # Additional logging of request details
                st.write("Debug: Full Order Request:")
                for key, value in order_request.items():
                    st.write(f"{key}: {value}")
                
                # Create logistics order
                with st.spinner("建立物流單中..."):
                    response = ECPayLogistics.create_logistics_order(order_request)
                    
                    # Log full response
                    st.write("Debug: API Response:")
                    st.json(response)
                    
                    if "RtnCode" in response and response["RtnCode"] == "1":
                        # Success - save to database if possible
                        logistics_save_data = {
                            "order_id": order_id,
                            "platform": platform,
                            "ecpay_logistics_id": response.get("AllPayLogisticsID", ""),
                            "merchant_trade_no": merchant_trade_no,
                            "logistics_type": "CVS",
                            "logistics_sub_type": order_request.get('LogisticsSubType', 'UNIMARTC2C'),
                            "store_id": order_request.get('ReceiverStoreID', ''),
                            "cvs_payment_no": response.get("CVSPaymentNo", ""),
                            "cvs_validation_no": response.get("CVSValidationNo", ""),
                            "status": response.get("RtnCode", ""),
                            "status_msg": response.get("RtnMsg", ""),
                            "tracking_number": ""
                        }
                        
                        # Attempt to save to database
                        try:
                            db.save_logistics_order(logistics_save_data)
                        except Exception as e:
                            st.warning(f"無法保存物流訂單: {str(e)}")
                        
                        st.success(f"綠界物流單建立成功！ID: {response.get('AllPayLogisticsID', '')}")
                    else:
                        # Error
                        error_msg = response.get("RtnMsg", "未知錯誤")
                        error_code = response.get("RtnCode", "")
                        st.error(f"建立物流單失敗: {error_msg} (錯誤代碼: {error_code})")
                    
            except Exception as e:
                st.error(f"建立物流單時發生錯誤: {str(e)}")
    
    with col2:
        # Always show print button
        if st.button("列印託運單", key=f"print_{order_id}"):
            try:
                # Debug print of input data
                st.write("Debug: Order Information")
                st.write(f"Order ID: {order_id}")
                st.write(f"Platform: {platform}")
                st.write("Logistics Data:", logistics_data)
                
                # Prepare query parameters
                query_params = {
                    'MerchantTradeNo': f"#{order_id}"
                }
                
                # Query logistics order
                query_response = ECPayLogistics.query_logistics_order(**query_params)
                
                # Check query results
                if query_response.get('error'):
                    st.error(f"查詢物流單失敗: {query_response.get('message', '未知錯誤')}")
                    st.write("查詢參數:", query_params)
                    return
                
                # Determine document type based on store ID
                store_id = logistics_data.get('store_id', '')
                document_type = "UNIMARTC2C"  # Default to 7-ELEVEN
                if store_id and store_id.startswith('1'):  # Assuming Family Mart stores start with 1
                    document_type = "FAMIC2C"
                
                # Print shipping document
                form_html = ECPayLogistics.print_shipping_document(
                    AllPayLogisticsID=query_response.get('AllPayLogisticsID'),
                    CVSPaymentNo=query_response.get('CVSPaymentNo'),
                    CVSValidationNo=query_response.get('CVSValidationNo', ''),
                    document_type=document_type
                )
                
                # Display the form for auto-submission
                st.components.v1.html(form_html, height=500, scrolling=True)
                st.success("正在開啟物流單列印視窗，請等待...")
            
            except Exception as e:
                st.error(f"列印託運單時發生錯誤: {str(e)}")
                import traceback
                st.error(traceback.format_exc())

@st.fragment
def shopify_ecpay_ui(order, db):
    """ECPay logistics UI for Shopify orders
    
    Args:
        order (dict): Shopify order data
        db: Database connection
    """
    # Extract information from note attributes
    def get_store_info_from_attributes(order):
        # Look for store info in note attributes
        note_attributes = order.get('note_attributes', [])
        store_info = {
            'cvs_company': None,
            'cvs_store_id': None,
            'logistics_subtype': 'UNIMARTC2C'  # Default to 7-ELEVEN
        }
        
        # Check order notes and attributes for store info
        for attr in note_attributes:
            name = str(attr.get('name', '')).lower()
            value = str(attr.get('value', ''))
            
            if '超商類型' in name or 'cvscompany' in name:
                if '7-eleven' in value.lower():
                    store_info['cvs_company'] = '7-ELEVEN'
                    store_info['logistics_subtype'] = 'UNIMARTC2C'
                elif '全家' in value.lower() or 'family' in value.lower():
                    store_info['cvs_company'] = '全家'
                    store_info['logistics_subtype'] = 'FAMIC2C'
            
            if '門市代號' in name or 'cvsstore' in name:
                store_info['cvs_store_id'] = value.strip()
        
        # Look in order notes
        order_note = order.get('note', '')
        if order_note:
            # Look for store ID pattern in notes
            import re
            store_id_match = re.search(r'門市代號.*[：:]\s*(\d+)', order_note)
            if store_id_match:
                store_info['cvs_store_id'] = store_id_match.group(1).strip()
            
            # Look for store type
            if '7-ELEVEN' in order_note:
                store_info['cvs_company'] = '7-ELEVEN'
                store_info['logistics_subtype'] = 'UNIMARTC2C'
            elif '全家' in order_note:
                store_info['cvs_company'] = '全家'
                store_info['logistics_subtype'] = 'FAMIC2C'
        
        return store_info
    
    # Get store info from order
    store_info = get_store_info_from_attributes(order)
    
    # Logistics options
    logistics_options = {
        "UNIMARTC2C": "7-ELEVEN 超商交貨便",
        "FAMIC2C": "全家店到店",
        "HILIFEC2C": "萊爾富店到店",
        "OKMARTC2C": "OK超商店到店"
    }
    
    with st.container():
        st.subheader("綠界物流設定")
        
        # Get customer info
        customer_name = f"{order.get('customer', {}).get('first_name', '')} {order.get('customer', {}).get('last_name', '')}".strip()
        
        # Get shipping address and phone
        shipping_address = order.get('shipping_address', {})
        phone = shipping_address.get('phone', '')
        
        # Calculate order total
        total_amount = int(float(order.get('total_price', '0')))
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("收件人資訊")
            receiver_name = st.text_input(
                "收件人姓名", 
                value=customer_name, 
                max_chars=10,  # Limit to 10 chars
                help="姓名長度限制2~5個中文字或4~10個英文字",
                key=f"name_{order['order_number']}"
            )
            receiver_phone = st.text_input(
                "收件人電話", 
                value=phone, 
                help="必須為09開頭的10碼數字",
                key=f"phone_{order['order_number']}"
            )
            receiver_email = st.text_input(
                "收件人 Email", 
                value=order.get('email', ''), 
                key=f"email_{order['order_number']}"
            )
        
        with col2:
            st.write("物流設定")
            # Pre-select based on detected store type
            default_logistics = store_info['logistics_subtype']
            default_index = list(logistics_options.keys()).index(default_logistics) if default_logistics in logistics_options else 0
            
            selected_logistics = st.selectbox(
                "物流類型",
                options=list(logistics_options.keys()),
                index=default_index,
                format_func=lambda x: logistics_options[x],
                key=f"logistics_{order['order_number']}"
            )
            
            # Pre-fill detected store ID
            store_id = st.text_input(
                "門市代號", 
                value=store_info['cvs_store_id'] or '',
                help="請填入正確的門市代號",
                key=f"store_{order['order_number']}"
            )
            
            goods_amount = st.number_input(
                "商品金額",
                min_value=1, 
                max_value=20000,
                value=total_amount,
                help="金額必須在1-20000之間",
                key=f"amount_{order['order_number']}"
            )
            
            is_collection = st.checkbox(
                "代收貨款",
                value=False,
                help="勾選後，收件人須支付商品金額",
                key=f"collection_{order['order_number']}"
            )
        
        # Prepare goods description
        items_desc = ", ".join([f"{item['title']} x {item['quantity']}" for item in order.get('line_items', [])][:3])
        if len(order.get('line_items', [])) > 3:
            items_desc += f" 等{len(order.get('line_items', []))}項商品"
            
        # Trim and clean description
        if len(items_desc) > 45:
            items_desc = items_desc[:45] + "..."
        
        import re
        items_desc = re.sub(r'[^\w\s\u4e00-\u9fff,.]', '', items_desc)
            
        goods_name = st.text_input(
            "商品描述",
            value=items_desc,
            max_chars=50,
            help="商品描述不可包含特殊符號，長度限制50字元",
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
        st.divider()
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
        
        items_desc = order.get('line_items', [])[0]['title'] if order.get('line_items') else '商品'
        items_desc = items_desc[:20]  # Keep it very short
        items_desc = re.sub(r'[^\w\s\u4e00-\u9fff,.]', '', items_desc)
            
        goods_name = st.text_input(
            "商品描述",
            value=items_desc,
            max_chars=25,
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