import streamlit as st
import grpc
import order_api_pb2
import order_api_pb2_grpc
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict
import pandas as pd

# --- gRPC Client Setup ---

# ที่อยู่ของเซิร์ฟเวอร์ (ที่เราแก้ไขเป็น 0.0.0.0:50051 ใน server.py)
GRPC_SERVER_ADDRESS = 'localhost:50051'

@st.cache_resource # ใช้ Cache เพื่อไม่ต้องเชื่อมต่อใหม่ทุกครั้งที่คลิก
def get_grpc_stubs():
    """
    สร้างและคืนค่า Stubs สำหรับเชื่อมต่อ gRPC
    """
    try:
        channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        # ทดสอบการเชื่อมต่อ (อาจใช้เวลาสักครู่หากเซิร์ฟเวอร์ยังไม่รัน)
        grpc.channel_ready_future(channel).result(timeout=5)
    except grpc.FutureTimeoutError:
        st.error(f"ไม่สามารถเชื่อมต่อไปยัง gRPC Server ที่ {GRPC_SERVER_ADDRESS} ได้")
        st.error("กรุณาตรวจสอบว่าคุณรัน `python server.py` ใน Terminal อีกอันหนึ่งแล้ว!")
        return None, None, None

    print(f"✅ Connected to gRPC server at {GRPC_SERVER_ADDRESS}")
    auth_stub = order_api_pb2_grpc.AuthServiceStub(channel)
    product_stub = order_api_pb2_grpc.ProductServiceStub(channel)
    order_stub = order_api_pb2_grpc.OrderServiceStub(channel)
    return auth_stub, product_stub, order_stub

# --- Main Application ---
st.set_page_config(layout="wide")
st.title("📦 gRPC API Dashboard (Web UI)")

# เรียก Stubs
auth_stub, product_stub, order_stub = get_grpc_stubs()

# ถ้าเชื่อมต่อไม่ได้ ก็ไม่ต้องทำอะไรต่อ
if not product_stub:
    st.stop()

# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("เลือกหน้า", ["Product Management", "Order Management"])

# ==================================
#       PAGE: Product Management
# ==================================
if page == "Product Management":
    st.header("Product Management")
    
    col1, col2 = st.columns([1, 1])

    # --- Column 1: Create Product ---
    with col1:
        st.subheader("➕ Create New Product")
        with st.form("new_product_form", clear_on_submit=True):
            name = st.text_input("Product Name")
            description = st.text_area("Description")
            price = st.number_input("Price", min_value=0.01, step=0.01, format="%.2f")
            
            submitted = st.form_submit_button("Create Product")
            
            if submitted:
                try:
                    req = order_api_pb2.CreateProductRequest(
                        name=name,
                        description=description,
                        price=price
                    )
                    new_product = product_stub.CreateProduct(req)
                    st.success(f"Product Created! ID: {new_product.product_id}")
                    st.json(MessageToDict(new_product))
                except grpc.RpcError as e:
                    st.error(f"Error creating product: {e.details()}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

    # --- Column 2: List Products ---
    with col2:
        st.subheader("📋 List All Products")
        if st.button("🔄 Refresh Product List"):
            try:
                # เรียก gRPC service 'ListProducts'
                products_response = product_stub.ListProducts(empty_pb2.Empty())
                
                # แปลงผลลัพธ์ (Generator) ให้อยู่ใน List of Dictionaries
                products_list = [MessageToDict(p) for p in products_response]
                
                if not products_list:
                    st.warning("No products found in the database.")
                else:
                    # แสดงผลด้วย Pandas DataFrame
                    df = pd.DataFrame(products_list)
                    st.dataframe(df)

            except grpc.RpcError as e:
                st.error(f"Error listing products: {e.details()}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

# ==================================
#       PAGE: Order Management
# ==================================
elif page == "Order Management":
    st.header("Order Management")
    st.write("ฟังก์ชันสำหรับจัดการ Order (เช่น ListOrders, GetOrder) จะถูกเพิ่มที่นี่")
    
    # (ตัวอย่าง)
    if st.button("🔄 Refresh Order List"):
        st.info("ยังไม่ได้สร้างฟังก์ชัน ListOrders ในเซิร์ฟเวอร์ครับ")