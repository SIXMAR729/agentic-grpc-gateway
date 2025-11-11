# --- Imports ---
import grpc
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict

# --- sys.path ---
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, root_dir)
print(f"DEBUG: Added root directory to import path: {root_dir}")

# --- New Import for calling Ollama ---
import requests

# --- gRPC Code Import ---
import order_api_pb2
import order_api_pb2_grpc
print(f"DEBUG: Successfully imported _grpc.py from: {order_api_pb2_grpc.__file__}")

# --- .env File Loading ---
script_dir = Path(__file__).parent
env_path = script_dir / ".env"
load_dotenv(dotenv_path=env_path)

# --- Configuration ---
API_SERVER_ADDRESS = 'localhost:50051'
OLLAMA_API_URL = "http://localhost:11434/api/chat"
print("DEBUG: Running in manual Ollama (local) mode. No API key needed.")

# --- Tool Definitions ---
TOOLS_DEFINITION = [
    {
        "name": "login",
        "description": "Authenticates a user and returns a JWT token for future requests.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "The user's username (e.g., 'admin')."},
                "password": {"type": "STRING", "description": "The user's password (e.g., 'admin123')."}
            },
            "required": ["username", "password"]
        }
    },
    {
        "name": "get_available_tools",
        "description": "ใช้ Tool นี้เมื่อ User ถามว่า 'คุณทำอะไรได้บ้าง' (What can you do?) เพื่อแสดงรายการเครื่องมือทั้งหมดที่ AI มี",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "list_products",
        "description": "Gets a list of all available products from the database.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
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
                "name": {"type": "STRING", "description": "The name of the new product."},
                "description": {"type": "STRING", "description": "A description for the product."},
                "price": {"type": "NUMBER", "description": "The price of the product (e.g., 19.99)."}
            },
            "required": ["name", "price"]
        }
    },
    {
        "name": "delete_product",
        "description": "Deletes a product from the database using its ID (REQUIRES 'admin' role).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "product_id": {"type": "STRING", "description": "The unique ID of the product to delete (e.g., 'prod-abc123')."}
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
                "order_id": {"type": "STRING", "description": "The unique ID of the order to retrieve (e.g., 'order-xyz789')."}
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
        "name": "search_products",
        "description": "ค้นหาสินค้าตามชื่อ (Search Query) และจำกัดจำนวนผลลัพธ์ (Limit)",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "search_query": {"type": "STRING", "description": "ชื่อสินค้า (หรือส่วนของชื่อ) ที่ต้องการค้นหา เช่น 'Laptop'"},
                "limit": {"type": "NUMBER", "description": "จำนวนผลลัพธ์สูงสุดที่ต้องการ เช่น 5"}
            },
            "required": ["search_query", "limit"]
        }
    },
    {
        "name": "create_order",
        "description": "Creates a new order for a specific user with a list of items.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {"type": "STRING", "description": "The unique ID of the user placing the order (e.g., 'user-123')."},
                "items": {
                    "type": "ARRAY",
                    "description": "A list of item objects to be included in the order.",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "product_id": {"type": "STRING", "description": "The unique ID of the product to order."},
                            "quantity": {"type": "NUMBER", "description": "The number of units to order."}
                        },
                        "required": ["product_id", "quantity"]
                    }
                }
            },
            "required": ["user_id", "items"]
        }
    }
]

# --- API Client Class ---
class APIClient:
    """Handles all communication with the gRPC server."""
    
    def __init__(self, address):
        self.auth_stub = None
        self.product_stub = None
        self.order_stub = None
        self.jwt_token = None
        try:
            self.channel = grpc.insecure_channel(address)
            grpc.channel_ready_future(self.channel).result(timeout=1)
            self.auth_stub = order_api_pb2_grpc.AuthServiceStub(self.channel)
            self.product_stub = order_api_pb2_grpc.ProductServiceStub(self.channel)
            self.order_stub = order_api_pb2_grpc.OrderServiceStub(self.channel)
            print("🔌 Connected to gRPC API server.")
        except grpc.FutureTimeoutError:
            print(f"❌ Error: Could not connect to the server at {address}.", file=sys.stderr)
            print("   Please ensure 'server.py' is running.", file=sys.stderr)

    def _get_auth_metadata(self):
        if not self.jwt_token:
            print("   Warning: No JWT token set. Call login() first.", file=sys.stderr)
            return []
        return [('authorization', f'Bearer {self.jwt_token}')]

    def _message_to_dict(self, message):
        return MessageToDict(message, preserving_proto_field_name=True)

    def _list_to_dict_list(self, message_list):
        return [self._message_to_dict(msg) for msg in message_list]

    # --- Auth Methods ---
    def login(self, username, password):
        
        print(f"[Agent is calling Login API for user: {username}...]") 
        try:
            request = order_api_pb2.LoginRequest(username=username, password=password)
            response = self.auth_stub.Login(request)
            if response.token:
                self.jwt_token = response.token
                
                role = getattr(response, "role", "unknown") #Avoid Error from .proto file
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
        print("[Agent is calling ListProducts API (Streaming)...]")
        response_stream = self.product_stub.ListProducts(empty_pb2.Empty())
        
        products_list = []
        count = 0
        limit_for_ai = 20 # ⬇️ [Can Adjust] Set Limit for small AI only 20 
        
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
            print(f"  Error receiving product stream: {e}", file=sys.stderr)
            return f"Error: {e.details()}"
        

            
   
    def search_products(self, search_query, limit):
        """
        เรียก RPC 'SearchProducts' แบบ Stream และแปลงเป็น List
        """
        print(f"[Agent is calling SearchProducts API (Query: {search_query}, Limit: {limit})...]")
        
        try:
            # 1. สร้าง Request object
            request = order_api_pb2.SearchProductsRequest(
                search_query=search_query,
                limit=int(limit) # AI อาจส่ง 5.0 มา, เราจึงต้องแปลงเป็น int
            )
            
            # 2. เรียก gRPC Stub และรับ "ท่อ" (Stream) กลับมา
            response_stream = self.product_stub.SearchProducts(request)
            
            products_list = []
            # 3. วน Loop ดึงข้อมูลจาก "ท่อ" ทีละชิ้น
            for product in response_stream:
                products_list.append(self._message_to_dict(product))
            
            # 4. คืนค่า List (ที่ตอนนี้มีขนาดเล็ก) กลับไปให้ AI
            return products_list
            
        except grpc.RpcError as e:
            print(f"  Error receiving search stream: {e}", file=sys.stderr)
            return f"Error: {e.details()}"
        except Exception as e:
            print(f"  Unexpected error in search_products: {e}", file=sys.stderr)
            return f"Error: {e}"
    # [เพิ่มใหม่] ⬆️ ⬆️ ⬆️ 

    def count_products(self):
        print("[Agent is calling CountProducts API...]")
        response = self.product_stub.CountProducts(empty_pb2.Empty())
        return self._message_to_dict(response)

    def get_product(self, product_id):
        return self.product_stub.GetProduct(order_api_pb2.GetProductRequest(product_id=product_id))

    def create_product(self, name, description, price):
        print(f"[Agent is calling CreateProduct API for: {name}...]") 
        request = order_api_pb2.CreateProductRequest(
            name=name,
            description=description,
            price=price
        )
        response = self.product_stub.CreateProduct(request)
        return self._message_to_dict(response)

    def delete_product(self, product_id):
        print(f"[Agent is calling DeleteProduct API for: {product_id}...]")
        request = order_api_pb2.DeleteProductRequest(product_id=product_id)
        response = self.product_stub.DeleteProduct(
            request, 
            metadata=self._get_auth_metadata()
        )
        return self._message_to_dict(response)

    # --- Order Methods ---
    def get_order(self, order_id):
        print(f"[Agent is calling GetOrder API for: {order_id}...]") 
        try:
            request = order_api_pb2.GetOrderRequest(order_id=order_id)
            response = self.order_stub.GetOrder(request)
            return self._message_to_dict(response)
        except grpc.RpcError as e:
            return f"Error: {e.details()}"

    def count_orders(self):
        print("[Agent is calling CountOrders API...]")
        response = self.order_stub.CountOrders(empty_pb2.Empty())
        return self._message_to_dict(response)

    def create_order(self, user_id, items):
        print(f"[Agent is calling CreateOrder API for user: {user_id}...]") 
        order_items = []
        for item in items:
            try:
                product = self.get_product(item['product_id'])
                if product.product_id:
                    order_items.append(
                        order_api_pb2.Order.Item(
                            product_id=item['product_id'],
                            quantity=int(item['quantity']),
                            price_per_item=product.price
                        )
                    )
                else:
                    print(f"  Warning: Could not find product with ID {item['product_id']}. Skipping.", file=sys.stderr)
            except grpc.RpcError as e:
                print(f"  Warning: RPC Error finding {item['product_id']}: {e.details()}. Skipping.", file=sys.stderr)
            except (KeyError, TypeError) as e:
                print(f"  Warning: Malformed item from AI {item}. Skipping. Error: {e}", file=sys.stderr)
        
        if not order_items:
            return "Error: Could not create order. No valid products were found or all were out of stock."
            
        request = order_api_pb2.CreateOrderRequest(user_id=user_id, items=order_items)
        response = self.order_stub.CreateOrder(request)
        return self._message_to_dict(response)


# --- *** MODIFIED *** AI Agent Class (Manual Ollama Version) ---
class AIAgent:
    """Manages the AI model (Qwen2) and conversation loop via direct API calls."""
    
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
        self.model_name = "qwen2:1.5b" # <-- *** MODIFIED: Set model name here ***
        
        # 1. Map tool names to the actual Python functions
        self.tool_functions = {
            "login": self.api_client.login,
            "list_products": self.api_client.list_products,
            "count_products": self.api_client.count_products,
            "create_product": self.api_client.create_product,
            "delete_product": self.api_client.delete_product,
            "get_order": self.api_client.get_order,
            "count_orders": self.api_client.count_orders,
            "create_order": self.api_client.create_order,
            "search_products": self.api_client.search_products,
            "get_available_tools": self.get_available_tools,
            "get_my_status": self.get_my_status,
        }
        
        # 2. Check if Ollama is running
        self._check_ollama()
        
        # 3. Create the master system prompt
        system_prompt = self._create_system_prompt()
        
        # 4. We must manually keep track of the conversation history
        self.chat_history = [
            {"role": "system", "content": system_prompt}
        ]
    
    def get_available_tools(self):
        """
        Tool ภายใน (Internal Tool) ที่คืนค่าชื่อ Tool ทั้งหมด
        """
        print("[Agent is calling internal tool: get_available_tools...]")
        
        # [แก้ไข] ⬇️
        # ตรวจสอบให้แน่ใจว่ามันเรียก 'self.tool_functions' (ไม่ใช่ 'self.api_client.tool_functions')
        tool_names = [name for name in self.tool_functions.keys() if name != "get_available_tools"]
        return {"available_tools": tool_names}

    def get_my_status(self):
        """
        Tool ภายใน (Internal Tool) ที่ตรวจสอบ "ความจำ" ของ Agent
        """
        print("🤖 AI is checking its internal memory for user role...")
        if self.current_user_role:
            return f"You are currently logged in. Your role is: {self.current_user_role}"
        else:
            return "You are not currently logged in, or your role is unknown."

    def _check_ollama(self):
        """Pings the Ollama server to ensure it's running."""
        print(f"🧠 Checking for Ollama server at http://localhost:11434 (using model: {self.model_name})...")
        try:
            response = requests.get("http://localhost:11434", timeout=3)
            response.raise_for_status()
            print("✅ Ollama server is responding.")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error: Could not connect to Ollama.", file=sys.stderr)
            print("   Please ensure Ollama is running on your machine.", file=sys.stderr)
            print(f"   Error details: {e}", file=sys.stderr)
            raise

    def _create_system_prompt(self):
        """Builds the large system prompt to teach the AI model how to use tools."""
        
        
        tools_json = json.dumps(TOOLS_DEFINITION)
        
        
        
        
        prompt_part_1 = """
You are a JSON-only assistant. You MUST always respond with a valid JSON object.
You have access to these tools:
"""
        
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
## Example Conversation

**User:** "how many products are there?"

**Assistant (You):** {{"tool_call": {{"name": "count_products", "arguments": {{}}}}}}

**User (System):** {{"tool_response": {{"name": "count_products", "result": "{\\"count\\": 5}"}}}}

**Assistant (You):** {{"response": "There are 5 products in the database."}}

---
## Important Rules
- Never respond with plain text.
- Always respond with one of the two JSON formats: `{{"tool_call": ...}}` or `{{"response": ...}}`.
- Do not try to answer from memory. Always call a tool.

Now, begin the conversation.
"""
        
        return prompt_part_1 + tools_json + prompt_part_2
    
    def _normalize_args(self, args):
        """
        Fixes malformed arguments from the AI.
        It can merge a list of dicts like [{'a': 1}, {'b': 2}]
        into a single dict {'a': 1, 'b': 2}.
        """
        if isinstance(args, dict):
            return args  
        
        if isinstance(args, list):
            print("   [Fixing AI args: Received a list, merging into one dict...]")
            normalized_args = {}
            for item in args:
                if isinstance(item, dict):
                    normalized_args.update(item)
            return normalized_args
            
        # Fallback for other weird types (like a string or int)
        print(f"   [Fixing AI args: Received unknown type {type(args)}, returning empty dict.]")
        return {}
    
    def handle_function_call(self, tool_call_data: dict):
        """Executes the tool function and returns its result."""
        func_name = tool_call_data.get("name")
        raw_args = tool_call_data.get("arguments", {})

        args = self._normalize_args(raw_args)
        
        print(f"[Agent is calling tool: {func_name} with args: {args}]")
        
        if func_name not in self.tool_functions:
            print(f"Error: Unknown tool '{func_name}'", file=sys.stderr)
            return {"error": f"Unknown tool '{func_name}'"}
            
        func = self.tool_functions[func_name]
        try:
            # Call the function (e.g., api_client.list_products())
            result = func(**args)
            return result
        except Exception as e:
            print(f"Error executing tool '{func_name}': {e}", file=sys.stderr)
            return {"error": str(e)}

    def run_conversation_loop(self):
        """Main conversation loop."""
        print("🤖 AI Agent is ready. Type 'exit' to end.")
        print("   Try asking: 'how many products are there?' or 'list all products'")
        
        while True:
            try:
                user_prompt = input("👤 You: ")
                if user_prompt.lower() == 'exit':
                    break

                # 1. Add user message to history
                self.chat_history.append({"role": "user", "content": user_prompt})

                print("🤖 AI is thinking...")
                
                # 2. Call Ollama API
                # We ask for JSON format, which forces the model to obey our system prompt
                payload = {
                    "model": self.model_name, 
                    "messages": self.chat_history,
                    "stream": False,
                    "format": "json"  
                }
                
                response = requests.post(OLLAMA_API_URL, json=payload)
                response.raise_for_status() # Check for HTTP errors
                
                # 3. Parse the AI's JSON response
                response_json_str = response.json()['message']['content']
                self.chat_history.append({"role": "assistant", "content": response_json_str})
                
                try:
                    ai_response = json.loads(response_json_str)
                except json.JSONDecodeError:
                    print(f"🤖 AI: (Sent invalid JSON, retrying) {response_json_str}")
                    self.chat_history.pop() # Remove the bad response
                    continue

                # 4. Check if it's a tool call or a text answer
                if "tool_call" in ai_response:
                    # 4a. It's a TOOL CALL
                    tool_call_data = ai_response['tool_call']
                    
                    # 5. Execute the tool
                    tool_result = self.handle_function_call(tool_call_data)
                    
                    # 6. Create the tool response message and add to history
                    tool_response_msg = {
                        "tool_response": {
                            "name": tool_call_data.get("name"),
                            "result": str(tool_result) # Convert result to string
                        }
                    }
                    self.chat_history.append({"role": "user", "content": json.dumps(tool_response_msg)})

                    # 7. Call Ollama AGAIN to get a final summary
                    print("🤖 AI is summarizing tool results...")
                    summary_payload = {
                        "model": self.model_name, # <-- *** MODIFIED: Use class variable ***
                        "messages": self.chat_history,
                        "stream": False,
                        "format": "json" # Ask for JSON again
                    }
                    
                    summary_response = requests.post(OLLAMA_API_URL, json=summary_payload)
                    summary_json_str = summary_response.json()['message']['content']
                    self.chat_history.append({"role": "assistant", "content": summary_json_str})
                    
                    try:
                        final_answer = json.loads(summary_json_str)
                        print(f"🤖 AI: {final_answer.get('response', 'Got tool result.')}")
                    except json.JSONDecodeError:
                        print(f"🤖 AI: (Sent invalid summary JSON) {summary_json_str}")
                
                elif "response" in ai_response:
                    # 4b. It's a plain TEXT ANSWER
                    print(f"🤖 AI: {ai_response['response']}")
                
                else:
                    print(f"🤖 AI: (Sent unexpected JSON) {ai_response}")

            except KeyboardInterrupt:
                break
            except requests.exceptions.RequestException as e:
                print(f"\nAn error occurred connecting to Ollama: {e}", file=sys.stderr)
                break
            except Exception as e:
                print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        
        print("🤖 AI Agent shutting down. Goodbye!")


# --- Main Execution Block (UNCHANGED) ---

def main():
    # Create an instance of the API client.
    api_client = APIClient(API_SERVER_ADDRESS)
    # Check if the connection was successful before continuing.
    if not api_client.product_stub or not api_client.order_stub or not api_client.auth_stub:
        print("Exiting due to gRPC connection failure.", file=sys.stderr)
        sys.exit(1) # Exit if it failed.
    
    try:
        # Create an instance of the AI agent.
        agent = AIAgent(api_client)
        # Start the conversation loop.
        agent.run_conversation_loop()
    except Exception as e:
        # Catches errors, like the Ollama connection failure
        print(f"Failed to initialize AI Agent: {e}", file=sys.stderr)
        sys.exit(1)

# This ensures the main() function is called only when the script is run directly.
if __name__ == '__main__':
    main()