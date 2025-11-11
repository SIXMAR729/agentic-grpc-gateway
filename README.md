# agentic-grpc-gateway
A Python gRPC gateway that provides a secure, "agentic" API for multiple clients (CLI, Streamlit UI, and a Local AI(Qwen,Phi-3)).

agentic-grpc-gateway 🚀
Welcome to the Agentic gRPC Gateway!

This is a complete backend project built with Python and gRPC. It functions as a secure gateway server, providing a single, unified API for managing a database of products, orders, and authentication.

This project doesn't just have one client; it's an architecture designed to support three distinct client interfaces, all connecting to the same server.

🏛️ Architecture
The core of this project is a clean separation between "logic" and "presentation."

Backend (server.py): A robust gRPC Server that acts as the single, authoritative Gatekeeper. It is the only component allowed to touch the database.

Clients (UI, CLI, AI): The "customers" who must communicate through the Gatekeeper. No client ever has direct access to the database (.db).

              [ ⌨️ product_cli.py ] ---.
                (For Administrators)   |
                                     |
[ 🎨 web_ui.py (Streamlit) ] ---+--- [ 🛡️ gRPC Server (server.py) ] <--> [ 🏦 SQLite DB ]
       (For GUI Users)               |     (Auth, Product, Order Services)
                                     |
       [ 🤖 run_agent.py (Ollama) ] ---'
           (AI Assistant)

✨ Key Features
gRPC Server: Built in Python with three core services:

AuthService: Manages user login and issues JWT Tokens.

ProductService: Manages product CRUD, search, and listing.

OrderService: Manages order creation and retrieval.

🔒 Security (Role-Based):

"Admin" (requires login) can perform all actions (CRUD).

"Guest" (no login required) has read-only access (e.g., search, list products).

The Server enforces these permissions by validating the JWT Token on protected methods.

⚡️ gRPC Streaming:

ListProducts and SearchProducts use Server-side Streaming (stream) to efficiently send large datasets to clients one piece at a time (preventing the AI from "choking" on data).

🤖 AI Agent Client (run_agent.py):

Uses a local AI (Ollama/Qwen2) as the "brain."

The AI is "taught" to use the gRPC services as its "Tools" (function calling).

The AI respects the Role-Based rules (e.g., it will refuse to delete if it hasn't login as an "admin").

⌨️ Admin CLI Client (product_cli.py):

A command-line client for administrators to directly manage the database (add, delete, search, export).

🎨 Web UI Client (web_ui.py):

An interactive dashboard built with Streamlit for visual, graphical data management.

🛠️ Tech Stack
Backend: Python, gRPC (grpcio, grpcio-tools)

Database: SQLite3

Security: PyJWT (for JSON Web Tokens)

AI Agent: Ollama (qwen2:1.5b), requests

Web UI: streamlit, pandas

CLI: argparse

Environment: python-dotenv

🚀 Getting Started
You will need Python 3.9+ and Ollama (if you wish to run the AI Agent) installed.

1. Installation
Clone the repository:

```Bash

git clone https://github.com/SIXMAR729/agentic-grpc-gateway.git
cd agentic-grpc-gateway
Create and Activate a Virtual Environment (venv):
```
```Bash

# (On Windows)
python -m venv venv
.\venv\Scripts\activate
Create a requirements.txt file: Create a new file named requirements.txt and paste in the following:
```
Plaintext

grpcio
grpcio-tools
protobuf
requests
python-dotenv
streamlit
pandas
PyJWT
passlib
bcrypt
Install Dependencies:

```Bash

pip install -r requirements.txt
Generate gRPC Code (Crucial Step): (Note that we point to the protos/ folder)
```
```Bash

python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. protos/order_api.proto
```
This will generate the necessary order_api_pb2.py and order_api_pb2_grpc.py files.

(For AI Agent) Set up Ollama:

Ensure you have Ollama installed and running on your machine.

Run this in your terminal to download the model:

```Bash

ollama pull qwen2:1.5b
```
🏃 How to Run
You will need at least 2 terminals open.

1. Terminal 1: Run the gRPC Server
This is the "heart" of the system. It must always be running first.

```Bash

# (Make sure your venv is active)
python server.py
Expected Output:

Starting gRPC server...
✅ gRPC server started and listening on 0.0.0.0:50051
2. Terminal 2: Choose Your Client
Pick one of these three clients to connect to your server:

A. Run the AI Agent (Ollama):
```
```Bash

# (Make sure venv is active and Ollama is running)
python run_agent.py
Expected Output:

DEBUG: Added root directory to import path: ...
DEBUG: Successfully imported _grpc.py from: ...
DEBUG: Running in manual Ollama (local) mode. No API key needed.
🧠 Checking for Ollama server at http://localhost:11434...
✅ Ollama server is responding.
🔌 Connected to gRPC API server.
🤖 AI Agent is ready. Type 'exit' to end.
👤 You:
B. Run the Admin CLI:
```
```Bash

# (Make sure venv is active)
# Try searching for a product (this is a "Guest" right and should work)
python product_cli.py search --query "Laptop"
C. Run the Web UI (Streamlit):
```
```Bash

# (MakeGg sure venv is active)
streamlit run web_ui.py
(Your browser will automatically open to http://localhost:8501)
```
🧑‍🔬 Usage Examples
Example: AI Agent (Role-Based Security)
This demonstrates the Role-Based security system.

1. Test "Guest" Permissions (Fails ❌)

👤 You: delete product prod-770d6554
🤖 AI is thinking...
[Agent is calling tool: delete_product with args: {'product_id': 'prod-770d6554'}]
[Agent is calling DeleteProduct API for: prod-770d6554...]
   Warning: No JWT token set. Call login() first.
Error executing tool 'delete_product': ... status = StatusCode.PERMISSION_DENIED
🤖 AI is summarizing tool results...
🤖 AI: I'm sorry, I encountered an error: 'Permission denied: 'admin' role required.'
(This is correct! The server rejected the "Guest".)

2. Test "Admin" Permissions (Succeeds ✅)

👤 You: call login tool with username "admin" and password "admin123"
🤖 AI is thinking...
[Agent is calling tool: login with args: {'username': 'admin', 'password': 'admin123'}]
[Agent is calling Login API for user: admin...]
🤖 AI is summarizing tool results...
🤖 AI: {'status': 'Login successful', 'username': 'admin', 'role': 'admin'}

👤 You: delete product prod-770d6554
🤖 AI is thinking...
[Agent is calling tool: delete_product with args: {'product_id': 'prod-770d6554'}]
[Agent is calling DeleteProduct API for: prod-770d6554...]
🤖 AI is summarizing tool results...
🤖 AI: The deletion of the product with ID prod-770d6554 has been successful.
(This is correct! The server authenticated the token and allowed the Admin.)

Example: Admin CLI
```Bash

# Count all products
python product_cli.py count

# Search for products (Case-insensitive)
python product_cli.py search --query "laptop" --limit 2

# Add a product (requires Admin rights, as defined in server.py)
python product_cli.py add --name "New Laptop" --price 1500 --description "A new model"

# Delete a product
python product_cli.py delete --id "prod-123456"

```
