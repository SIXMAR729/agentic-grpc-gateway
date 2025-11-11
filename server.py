import grpc
import sqlite3
import uuid
import json
from concurrent import futures
from contextlib import contextmanager
from datetime import datetime, timedelta
import jwt

import order_api_pb2
import order_api_pb2_grpc
from google.protobuf import empty_pb2

# --- Configuration ---
DATABASE_NAME = "orders.db"
JWT_SECRET = "your-super-secret-key-that-should-be-in-an-env-variable"

def get_role_from_context(context, secret):
    """
    Helper "Guest": Checking for Token in metadata and ruturn to 'role'
    """
    metadata = dict(context.invocation_metadata())
    auth_header = metadata.get('authorization', None)
    
    if not auth_header:
        
        return "guest" # "guest" Role

    try:
        token_type, token = auth_header.split(' ')
        if token_type.lower() != 'bearer':
            return "guest" 
            
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload.get('role', "guest") # Return role (Example "admin")
        
    except jwt.ExpiredSignatureError:
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Token has expired.")
        return None # Expired Token
    except Exception as e:
        print(f"Token validation error: {e}")
        return "guest" # 

class Database:
    """Manages all database operations for the API."""
    def __init__(self, db_name):
        self.db_name = db_name
        self._init_db()

    def _init_db(self):
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                description TEXT, price REAL NOT NULL
            )""")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                status INTEGER NOT NULL, total_amount REAL NOT NULL
            )""")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                product_id TEXT NOT NULL, quantity INTEGER NOT NULL, price_per_item REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders (order_id)
            )""")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL
            )""")
            cursor.execute("SELECT * FROM users WHERE username='admin'")
            if not cursor.fetchone():
                admin_id = "user-" + str(uuid.uuid4())[:8]
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (admin_id, 'admin', 'admin123', 'admin'))
                conn.commit()

    @contextmanager
    def _get_connection(self):
        
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --- User Methods ---
    def get_user_by_username(self, username):
        
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
    

    # --- Product Methods ---
    
    def create_product(self, name, description, price):
   
        with self._get_connection() as conn:
            cursor = conn.cursor()
            while True:
                product_id = "prod-" + str(uuid.uuid4())[:8]
                cursor.execute("SELECT 1 FROM products WHERE product_id = ?", (product_id,))
                if not cursor.fetchone():
                    break
            
            cursor.execute("INSERT INTO products (product_id, name, description, price) VALUES (?, ?, ?, ?)", 
                           (product_id, name, description, price))
            
            conn.commit()
            
            
            row = cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
            return row
     

    def get_product(self, product_id):
        
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()

    def update_product(self, product_id, name, description, price):
        
        with self._get_connection() as conn:
            cursor = conn.execute("UPDATE products SET name=?, description=?, price=? WHERE product_id=?",
                                  (name, description, price, product_id))
            conn.commit()
            if cursor.rowcount == 0:
                return None
            return self.get_product(product_id)

    def delete_product(self, product_id): 
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_products(self):
        
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM products").fetchall()

    def count_products(self):
        
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    def export_products(self):
        
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM products").fetchall()
            return json.dumps([dict(row) for row in rows], indent=2)

    # --- Order Methods ---
    
    def create_order(self, user_id, items):
        total_amount = sum(item.quantity * item.price_per_item for item in items)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            while True:
                order_id = "order-" + str(uuid.uuid4())[:8]
                cursor.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,))
                if not cursor.fetchone():
                    break
            cursor.execute("INSERT INTO orders (order_id, user_id, status, total_amount) VALUES (?, ?, ?, ?)",
                         (order_id, user_id, order_api_pb2.Order.PENDING, total_amount))
            for item in items:
                cursor.execute("INSERT INTO order_items (order_id, product_id, quantity, price_per_item) VALUES (?, ?, ?, ?)",
                             (order_id, item.product_id, item.quantity, item.price_per_item))
            conn.commit()
        return self.get_order(order_id)

    def get_order(self, order_id):
        with self._get_connection() as conn:
            order_data = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if not order_data:
                return None, []
            items_data = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
            return order_data, items_data
    
    def update_order_status(self, order_id, new_status):
        with self._get_connection() as conn:
            cursor = conn.execute("UPDATE orders SET status=? WHERE order_id=?", (new_status, order_id))
            conn.commit()
            if cursor.rowcount == 0:
                return None, []
        return self.get_order(order_id)
        
    def count_orders(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

    def export_orders(self):
        with self._get_connection() as conn:
            orders_rows = conn.execute("SELECT * FROM orders").fetchall()
            items_rows = conn.execute("SELECT * FROM order_items").fetchall()
        
        orders_list = []
        for order_row in orders_rows:
            order_dict = dict(order_row)
            order_dict['items'] = [dict(item_row) for item_row in items_rows if item_row['order_id'] == order_dict['order_id']]
            orders_list.append(order_dict)
        return json.dumps(orders_list, indent=2)

# --- AuthService ---
class AuthServiceServicer(order_api_pb2_grpc.AuthServiceServicer):
    def __init__(self, db):
        self.db = db

    def Login(self, request, context):
        print(f"Login attempt for username: {request.username}")
        user_row = self.db.get_user_by_username(request.username)
        
        if user_row and user_row["password_hash"] == request.password:
            payload = {
                "user_id": user_row["user_id"],
                "role": user_row["role"],
                "exp": datetime.utcnow() + timedelta(hours=8)
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
            print(f"Login successful for user: {user_row['user_id']}")
            
            # [แก้ไข] ตรวจสอบว่า .proto มี 'role' หรือไม่
            if hasattr(order_api_pb2.LoginResponse(), 'role'):
                return order_api_pb2.LoginResponse(token=token, role=user_row["role"])
            else:
                return order_api_pb2.LoginResponse(token=token) # .proto เวอร์ชันเก่า
        else:
            print("Login failed: Invalid credentials.")
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details("Invalid username or password")
            return order_api_pb2.LoginResponse()

# --- ProductService ---
class ProductServiceServicer(order_api_pb2_grpc.ProductServiceServicer):
    def __init__(self, db):
        self.db = db

    def CreateProduct(self, request, context):
        
        row = self.db.create_product(request.name, request.description, request.price)
        if row is None:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to create product or retrieve it after creation.")
            return order_api_pb2.Product()
        return order_api_pb2.Product(**row)

    def GetProduct(self, request, context):
        row = self.db.get_product(request.product_id)
        if not row:
            context.set_code(grpc.StatusCode.NOT_FOUND); context.set_details("Product not found.")
            return order_api_pb2.Product()
        return order_api_pb2.Product(**row)

    def UpdateProduct(self, request, context):
        row = self.db.update_product(request.product_id, request.name, request.description, request.price)
        if not row:
            context.set_code(grpc.StatusCode.NOT_FOUND); context.set_details("Product not found to update.")
            return order_api_pb2.Product()
        return order_api_pb2.Product(**row)

    def DeleteProduct(self, request, context):
        role = get_role_from_context(context, JWT_SECRET)
        if role != "admin":
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details("Permission denied: 'admin' role required.")
            return order_api_pb2.DeleteProductResponse(success=False)
        success = self.db.delete_product(request.product_id)
        return order_api_pb2.DeleteProductResponse(success=success)

   
    def ListProducts(self, request, context):
        print("[User is calling ListProducts API (Streaming)...]")
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM products")
                
                
                for row in cursor:
                    
                    yield order_api_pb2.Product(**row)
                    
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Client ยกเลิก Product Stream (ทั้งหมด)")
            else:
                print(f"Stream error (All): {e}")
        except Exception as e:
            print(f"Internal stream error (All): {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"An internal error occurred: {e}")
            
        print("Product Stream (ทั้งหมด) สิ้นสุดลง")
   
    def SearchProducts(self, request, context):
        search_query = request.search_query
        limit = request.limit
        
        if limit <= 0 or limit > 100:
            limit = 10 

        print(f"Client ร้องขอ Product Stream (Search: '{search_query}', Limit: {limit})...")
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                
                sql_query = "SELECT * FROM products WHERE UPPER(name) LIKE UPPER(?) LIMIT ?"
                params = (f"%{search_query}%", limit)
                
                cursor.execute(sql_query, params)
                
                for row in cursor:
                    yield order_api_pb2.Product(**row)
                    
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Client ยกเลิก Product Stream (Search)")
            else:
                print(f"Stream error (Search): {e}")
        except Exception as e:
            print(f"Internal stream error (Search): {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"An internal error occurred: {e}")
            
        print("Product Stream (Search) สิ้นสุดลง")
    

    def CountProducts(self, request, context):
        count = self.db.count_products()
        return order_api_pb2.CountResponse(count=count)
    
    def ExportProducts(self, request, context):
        
        json_data = self.db.export_products()
        return order_api_pb2.ExportResponse(json_data=json_data)

# --- OrderService  ---
class OrderServiceServicer(order_api_pb2_grpc.OrderServiceServicer):
    def __init__(self, db):
        self.db = db

    def CreateOrder(self, request, context):
        order_row, item_rows = self.db.create_order(request.user_id, request.items)
        if not order_row:
             context.set_code(grpc.StatusCode.INTERNAL); context.set_details("Failed to create order.")
             return order_api_pb2.Order()
        items = [order_api_pb2.Order.Item(**item) for item in item_rows]
        return order_api_pb2.Order(**order_row, items=items)

    def GetOrder(self, request, context):
        order_row, item_rows = self.db.get_order(request.order_id)
        if not order_row:
            context.set_code(grpc.StatusCode.NOT_FOUND); context.set_details("Order not found.")
            return order_api_pb2.Order()
        items = [order_api_pb2.Order.Item(**item) for item in item_rows]
        return order_api_pb2.Order(**order_row, items=items)

    def UpdateOrderStatus(self, request, context):
        order_row, item_rows = self.db.update_order_status(request.order_id, request.new_status)
        if not order_row:
            context.set_code(grpc.StatusCode.NOT_FOUND); context.set_details("Order not found to update.")
            return order_api_pb2.Order()
        items = [order_api_pb2.Order.Item(**item) for item in item_rows]
        return order_api_pb2.Order(**order_row, items=items)
        
    def CountOrders(self, request, context):
        count = self.db.count_orders()
        return order_api_pb2.CountResponse(count=count)

    def ExportOrders(self, request, context):
        json_data = self.db.export_orders()
        return order_api_pb2.ExportResponse(json_data=json_data)

# --- Server Startup  ---
def serve():
    db = Database(DATABASE_NAME)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    order_api_pb2_grpc.add_AuthServiceServicer_to_server(AuthServiceServicer(db), server)
    order_api_pb2_grpc.add_ProductServiceServicer_to_server(ProductServiceServicer(db), server)
    order_api_pb2_grpc.add_OrderServiceServicer_to_server(OrderServiceServicer(db), server)
    
    port = '0.0.0.0:50051'
    server.add_insecure_port(port)
    
    server.start()
    
    print(f"✅ gRPC server started and listening on {port}")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Stopping server...")
        server.stop(0)

if __name__ == '__main__':
    print("Starting gRPC server...")
    serve()