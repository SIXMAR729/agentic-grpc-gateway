import streamlit as st
import grpc
import order_api_pb2
import order_api_pb2_grpc
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict
import pandas as pd
import requests  
import json      
import os        
import sys       

# --- sys.path ---

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, '.'))
sys.path.insert(0, root_dir)
print(f"DEBUG: Added root directory to import path: {root_dir}")

# --- Configuration (For AI) ---
OLLAMA_API_URL = "http://localhost:11434/api/chat"
GRPC_SERVER_ADDRESS = 'localhost:50051'


TOOLS_DEFINITION = [
    {
        "name": "login",
        "description": "Authenticates a user and returns a JWT token for future requests.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING"},
                "password": {"type": "STRING"}
            },
            "required": ["username", "password"]
        }
    },
    {
        "name": "logout",
        "description": "Logs out the current user, clears their 'admin' token, and reverts them to 'guest' status.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "get_my_status",
        "description": "Returns the status and role (e.g., admin, user) of the person currently logged in.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "get_available_tools",
        "description": "ใช้ Tool นี้เมื่อ User ถามว่า 'คุณทำอะไรได้บ้าง' (What can you do?)",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "list_products",
        "description": "ดึงสินค้า *ทั้งหมด* ในฐานข้อมูล (ถูกจำกัดที่ 20 ชิ้นสำหรับ AI)",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "search_products",
        "description": "ค้นหาสินค้าตามชื่อ (Search Query) และจำกัดจำนวนผลลัพธ์ (Limit)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "search_query": {"type": "STRING"},
                "limit": {"type": "NUMBER"}
            },
            "required": ["search_query", "limit"]
        }
    },
    {
        "name": "count_products",
        "description": "Returns the total number of products in the database.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "create_product",
        "description": "Creates a new product in the database (REQUIRES 'admin' role).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "description": {"type": "STRING"},
                "price": {"type": "NUMBER"}
            },
            "required": ["name", "price"]
        }
    },
    {
        "name": "update_product_name",
        "description": "อัปเดต *เฉพาะชื่อ* ของสินค้า (Requires 'admin' role)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_id": {"type": "STRING"},
                "new_name": {"type": "STRING"}
            },
            "required": ["product_id", "new_name"]
        }
    },
    {
        "name": "update_product_description",
        "description": "อัปเดต *เฉพาะรายละเอียด* ของสินค้า (Requires 'admin' role)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_id": {"type": "STRING"},
                "new_description": {"type": "STRING"}
            },
            "required": ["product_id", "new_description"]
        }
    },
    {
        "name": "update_product_price",
        "description": "อัปเดต *เฉพาะราคา* ของสินค้า (Requires 'admin' role)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_id": {"type": "STRING"},
                "new_price": {"type": "NUMBER"}
            },
            "required": ["product_id", "new_price"]
        }
    },
    {
        "name": "delete_product",
        "description": "Deletes a product by its ID (REQUIRES 'admin' role).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_id": {"type": "STRING"}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "get_order",
        "description": "Retrieves the full details of a specific order using its ID.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "order_id": {"type": "STRING"}
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "count_orders",
        "description": "Returns the total number of orders in the database.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "create_order",
        "description": "Creates a new order for a specific user with a list of items.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING"},
                "items": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "product_id": {"type": "STRING"},
                            "quantity": {"type": "NUMBER"}
                        },
                        "required": ["product_id", "quantity"]
                    }
                }
            },
            "required": ["user_id", "items"]
        }
    }
]

# --- gRPC Connection ---
# 6. [แก้ไข] เราจะปรับปรุงฟังก์ชัน gRPC ของคุณเล็กน้อย
#    เราจะ "แคช" stubs แยกกัน เพื่อให้ APIClient นำไปใช้ได้
@st.cache_resource
def get_grpc_channel():
    """สร้างและคืนค่า Channel (ท่อเชื่อมต่อ)"""
    try:
        channel = grpc.insecure_channel(GRPC_SERVER_ADDRESS)
        grpc.channel_ready_future(channel).result(timeout=5)
        return channel
    except grpc.FutureTimeoutError:
        st.error(f"ไม่สามารถเชื่อมต่อไปยัง gRPC Server ที่ {GRPC_SERVER_ADDRESS} ได้")
        st.error("กรุณาตรวจสอบว่าคุณรัน `python server.py` ใน Terminal อีกอันหนึ่งแล้ว!")
        return None

@st.cache_resource
def get_stubs(_channel):
    """สร้าง Stubs (ตัวควบคุม) จาก Channel"""
    if _channel is None:
        return None, None, None
    auth_stub = order_api_pb2_grpc.AuthServiceStub(_channel)
    product_stub = order_api_pb2_grpc.ProductServiceStub(_channel)
    order_stub = order_api_pb2_grpc.OrderServiceStub(_channel)
    return auth_stub, product_stub, order_stub


class APIClient:
    """Handles all communication with the gRPC server."""
    
    def __init__(self, auth_stub, product_stub, order_stub):
       
        self.auth_stub = auth_stub
        self.product_stub = product_stub
        self.order_stub = order_stub
        self.jwt_token = None
        

   
    def _get_auth_metadata(self):
        if not self.jwt_token:
            
            st.toast("⚠️ Warning: No JWT token set. Call login() first.")
            return []
        return [('authorization', f'Bearer {self.jwt_token}')]

    def _message_to_dict(self, message):
        return MessageToDict(message, preserving_proto_field_name=True)

    def _list_to_dict_list(self, message_list):
        return [self._message_to_dict(msg) for msg in message_list]

    # --- Auth Methods ---
    def login(self, username, password):
        try:
            request = order_api_pb2.LoginRequest(username=username, password=password)
            response = self.auth_stub.Login(request)
            if response.token:
                self.jwt_token = response.token
                role = getattr(response, "role", "unknown")
                return {
                    "status": "Login successful",
                    "username": username,
                    "role": role 
                }
            return "Login failed: No token received."
        except grpc.RpcError as e:
            return f"Error: {e.details()}"
        
    # --- Product Methods ---
    def list_products(self):
        response_stream = self.product_stub.ListProducts(empty_pb2.Empty())
        products_list = []
        count = 0
        limit_for_ai = 20
        try:
            for product in response_stream:
                if count < limit_for_ai:
                    products_list.append(self._message_to_dict(product))
                count += 1
            if count > limit_for_ai:
                summary_message = f"Found {count} total products, but only showing the first {limit_for_ai}."
                return {"summary": summary_message, "products": products_list}
            else:
                return {"summary": f"Found {count} products.", "products": products_list}
        except grpc.RpcError as e:
            st.error(f"Stream Error: {e.details()}")
            return f"Error: {e.details()}"
            
    def search_products(self, search_query="", limit=5):
        if not search_query:
            st.toast("Redirecting 'search' to 'list_products'")
            return self.list_products()
        try:
            request = order_api_pb2.SearchProductsRequest(
                search_query=search_query,
                limit=int(limit)
            )
            response_stream = self.product_stub.SearchProducts(request)
            products_list = []
            for product in response_stream:
                products_list.append(self._message_to_dict(product))
            return products_list
        except grpc.RpcError as e:
            st.error(f"Search Error: {e.details()}")
            return f"Error: {e.details()}"

    def count_products(self):
        response = self.product_stub.CountProducts(empty_pb2.Empty())
        return self._message_to_dict(response)

    def get_product(self, product_id):
        return self.product_stub.GetProduct(order_api_pb2.GetProductRequest(product_id=product_id))

    def create_product(self, name, description, price):
        request = order_api_pb2.CreateProductRequest(name=name, description=description, price=price)
        response = self.product_stub.CreateProduct(request, metadata=self._get_auth_metadata())
        return self._message_to_dict(response)
    
    def update_product_price(self, product_id, new_price):
        try:
            request = order_api_pb2.UpdateProductPriceRequest(product_id=product_id, new_price=float(new_price))
            response = self.product_stub.UpdateProductPrice(request, metadata=self._get_auth_metadata())
            return self._message_to_dict(response)
        except grpc.RpcError as e: return f"Error: {e.details()}"

    def update_product_name(self, product_id, new_name):
        try:
            request = order_api_pb2.UpdateProductNameRequest(product_id=product_id, new_name=new_name)
            response = self.product_stub.UpdateProductName(request, metadata=self._get_auth_metadata())
            return self._message_to_dict(response)
        except grpc.RpcError as e: return f"Error: {e.details()}"

    def update_product_description(self, product_id, new_description):
        try:
            request = order_api_pb2.UpdateProductDescriptionRequest(product_id=product_id, new_description=new_description)
            response = self.product_stub.UpdateProductDescription(request, metadata=self._get_auth_metadata())
            return self._message_to_dict(response)
        except grpc.RpcError as e: return f"Error: {e.details()}"

    def delete_product(self, product_id):
        request = order_api_pb2.DeleteProductRequest(product_id=product_id)
        response = self.product_stub.DeleteProduct(request, metadata=self._get_auth_metadata())
        return self._message_to_dict(response)

    # --- Order Methods ---
    def get_order(self, order_id):
        try:
            request = order_api_pb2.GetOrderRequest(order_id=order_id)
            response = self.order_stub.GetOrder(request)
            return self._message_to_dict(response)
        except grpc.RpcError as e: return f"Error: {e.details()}"

    def count_orders(self):
        response = self.order_stub.CountOrders(empty_pb2.Empty())
        return self._message_to_dict(response)

    def create_order(self, user_id, items):
        order_items = []
        for item in items:
            try:
                product = self.get_product(item['product_id'])
                if product.product_id:
                    order_items.append(order_api_pb2.Order.Item(
                        product_id=item['product_id'],
                        quantity=int(item['quantity']),
                        price_per_item=product.price
                    ))
            except (grpc.RpcError, KeyError, TypeError) as e:
                st.warning(f"Warning: Malformed/Invalid item {item}. Skipping.")
        
        if not order_items:
            return "Error: No valid products were found."
            
        request = order_api_pb2.CreateOrderRequest(user_id=user_id, items=order_items)
        response = self.order_stub.CreateOrder(request, metadata=self._get_auth_metadata())
        return self._message_to_dict(response)


class AIAgent:
    """Manages the AI model (Ollama) and conversation loop."""
    
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
        self.model_name = "qwen2:1.5b" # หรือ "phi3"
        self.current_user_role = None 
        
        self.tool_functions = {
            "login": self.api_client.login,
            "logout": self.logout,
            "list_products": self.api_client.list_products,
            "count_products": self.api_client.count_products,
            "search_products": self.api_client.search_products,
            "create_product": self.api_client.create_product,
            "update_product_name": self.api_client.update_product_name,
            "update_product_description": self.api_client.update_product_description,
            "update_product_price": self.api_client.update_product_price,
            "delete_product": self.api_client.delete_product,
            "get_order": self.api_client.get_order,
            "count_orders": self.api_client.count_orders,
            "create_order": self.api_client.create_order,
            "get_available_tools": self.get_available_tools,
            "get_my_status": self.get_my_status,
        }
        
       
        self.system_prompt = self._create_system_prompt()
        
     

    # --- Internal Tools ---

    def logout(self):
        """
        (Internal Tool): Clearing Token and Role from User
        """
        print("[Agent is calling internal tool: logout...]")
        
        
        self.current_user_role = None 
        
        
        if self.api_client:
            self.api_client.jwt_token = None
            
        return "You have been successfully logged out and reverted to 'guest' status."
    
    def get_available_tools(self):
        st.toast("Agent called: get_available_tools")
        tool_names = [name for name in self.tool_functions.keys() if name != "get_available_tools"]
        return {"available_tools": tool_names}

    def get_my_status(self):
        st.toast("Agent called: get_my_status")
        if self.current_user_role:
            return f"You are currently logged in. Your role is: {self.current_user_role}"
        else:
            return "You are not currently logged in, or your role is unknown."

    # --- Prompt & Tool Handling  ---
    def _create_system_prompt(self):
        tools_json = json.dumps(TOOLS_DEFINITION)
        prompt_part_1 = "You are a JSON-only assistant... (คัดลอก System Prompt ทั้งหมดของคุณมาวางที่นี่)"
    
        prompt_part_2 = """
---
## Your Task
Your job is to help the user by calling tools.
1.  **When the user asks a question** (like "how many products?"):
    You MUST respond with a JSON object to call a tool.
    The format is: {{"tool_call": {{"name": "tool_name", "arguments": {{"arg1": "value1"}}}}}}
2.  **When the system gives you a tool result** (like `tool_response`):
    You MUST respond with a final answer.
    The format is: {{"response": "Your final text answer."}}
---
## Important Rules
- Never respond with plain text.
- Always respond with one of the two JSON formats: `{{"tool_call": ...}}` or `{{"response": ...}}`.
- Do not try to answer from memory. Always call a tool.
Now, begin the conversation.
"""
        return prompt_part_1 + tools_json + prompt_part_2
    
    def _normalize_args(self, args):
        if isinstance(args, dict): return args
        if isinstance(args, list):
            normalized_args = {}
            for item in args:
                if isinstance(item, dict): normalized_args.update(item)
            return normalized_args
        return {}
    
    def handle_function_call(self, tool_call_data: dict):
        func_name = tool_call_data.get("name")
        raw_args = tool_call_data.get("arguments", {})
        args = self._normalize_args(raw_args)
        
        st.toast(f"🤖 Agent is calling tool: {func_name}")
        
        if func_name not in self.tool_functions:
            return {"error": f"Unknown tool '{func_name}'"}, None
            
        func = self.tool_functions[func_name]
        try:
            result = func(**args)
            
            if func_name == "login" and isinstance(result, dict) and "role" in result:
                self.current_user_role = result["role"]
            
            
            summary = None 
            if func_name == 'delete_product':
                product_id = args.get('product_id', 'unknown_id')
                if isinstance(result, dict) and result.get('success') and "product" in result:
                    summary = f"Successfully deleted product: '{result['product'].get('name', 'N/A')}'"
                else:
                    summary = f"Failed to delete product {product_id}. Result: {result}"
            
            elif func_name == 'update_product_price':
                 if isinstance(result, dict) and "product_id" in result:
                    summary = f"Successfully updated price for product '{result.get('name')}' to {result.get('price')}."
            
            
            
            return result, summary
            
        except Exception as e:
            st.error(f"Error executing tool '{func_name}': {e}")
            return {"error": str(e)}, None

   
    def get_response(self, user_prompt, chat_history):
        messages_to_send = [{"role": "system", "content": self.system_prompt}]
        
        for msg in chat_history:
            messages_to_send.append({"role": msg["role"], "content": msg["content"]})
        
        messages_to_send.append({"role": "user", "content": user_prompt})

        try:
            
            with st.spinner("🤖 AI is thinking..."):
                payload = {"model": self.model_name, "messages": messages_to_send, "stream": False, "format": "json"}
                response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
                response.raise_for_status()
            
            response_json_str = response.json()['message']['content']
            
            
            messages_to_send.append({"role": "assistant", "content": response_json_str})
            
            try:
                ai_response = json.loads(response_json_str)
            except json.JSONDecodeError:
                st.error(f"AI sent invalid JSON: {response_json_str}")
                return "AI sent an invalid response, please try again."

            
            if "tool_call" in ai_response:
                tool_call_data = ai_response['tool_call']
                
                
                tool_result, summary_message = self.handle_function_call(tool_call_data)
                
                
                if summary_message:
                    
                    return summary_message
                
                
                tool_response_msg = {"tool_response": {"name": tool_call_data.get("name"), "result": json.dumps(tool_result)}}
                messages_to_send.append({"role": "user", "content": json.dumps(tool_response_msg)})
                
                with st.spinner("🤖 AI is summarizing..."):
                    summary_payload = {"model": self.model_name, "messages": messages_to_send, "stream": False, "format": "json"}
                    summary_response = requests.post(OLLAMA_API_URL, json=summary_payload, timeout=60)
                    summary_json_str = summary_response.json()['message']['content']
                
                try:
                    final_answer = json.loads(summary_json_str)
                    return final_answer.get('response', 'Got tool result.')
                except json.JSONDecodeError:
                    st.error(f"AI sent invalid summary JSON: {summary_json_str}")
                    return "AI failed to summarize the result."
            
            elif "response" in ai_response:
                
                return ai_response['response']
            
            else:
                st.error(f"AI sent unexpected JSON: {ai_response}")
                return "AI response was not understood."

        except requests.exceptions.RequestException as e:
            st.error(f"Error connecting to Ollama at {OLLAMA_API_URL}")
            st.error("กรุณาตรวจสอบว่า Ollama Server ของคุณกำลังทำงาน!")
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            return None
    


# --- Streamlit Main Application ---
st.set_page_config(layout="wide")
st.title("📦 gRPC API Dashboard (Web UI)")


channel = get_grpc_channel()
auth_stub, product_stub, order_stub = get_stubs(channel)


if not channel:
    st.stop()


if "agent" not in st.session_state:
    print("Initializing AI Agent...")
   
    api_client = APIClient(auth_stub, product_stub, order_stub)
    
    st.session_state.agent = AIAgent(api_client)
    
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] # History สำหรับแสดงใน UI

# --- Sidebar Navigation ---
st.sidebar.title("Navigation")
# [แก้ไข] ⬇️ เพิ่มหน้า "AI Chatbot"
page = st.sidebar.radio("เลือกหน้า", ["Product Management", "Order Management", "🤖 AI Chatbot"])

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
                        name=name, description=description, price=price
                    )
                   
                    token = st.session_state.agent.api_client.jwt_token
                    metadata = [('authorization', f'Bearer {token}')] if token else []
                    
                    new_product = product_stub.CreateProduct(req, metadata=metadata)
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
                
                products_response_stream = product_stub.ListProducts(empty_pb2.Empty())
                
               
                with st.spinner("Loading products from stream..."):
                    products_list = [MessageToDict(p) for p in products_response_stream]
                
                if not products_list:
                    st.warning("No products found in the database.")
                else:
                    df = pd.DataFrame(products_list)
                    st.dataframe(df) # แสดงผล

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
    
    if st.button("🔄 Refresh Order List"):
        st.info("Not Found ListOrders in Server")

# ==================================
#       [เพิ่มใหม่] PAGE: AI Chatbot
# ==================================
elif page == "🤖 AI Chatbot":
    st.header("🤖 Agentic Gateway Chatbot")
    st.info("AI Agent connecting with gRPC Gateway directly Try out!")

    
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"]) 

    
    if prompt := st.chat_input("สั่งงาน AI (เช่น 'list all products' หรือ 'login as admin')..."):
        
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
       
        ai_agent = st.session_state.agent
        
        
        response_text = ai_agent.get_response(
            user_prompt=prompt,
            chat_history=st.session_state.chat_history[:-1] 
        )

        
        if response_text:
            with st.chat_message("assistant"):
                st.write(response_text)
            
            
            st.session_state.chat_history.append({"role": "assistant", "content": response_text})