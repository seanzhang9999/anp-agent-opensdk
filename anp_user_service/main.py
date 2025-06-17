from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from anp_user_service.app.routers import auth, chat

app = FastAPI(title="MCP Chat Extension Backend")

# CORS (Cross-Origin Resource Sharing)
# Allow your Chrome extension to call this API
# Replace "chrome-extension://<YOUR_EXTENSION_ID>" with your actual extension ID
# or use "*" for development (less secure).
origins = [
    "http://localhost", # If testing UI locally
    "http://localhost:8080", # Common dev server port
    "null", # For local file testing if popup is opened directly
    # "chrome-extension://your_chrome_extension_id_here" # IMPORTANT for production
    "chrome-extension://djlkliaeodleddflahameeolknjgikdl"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/agent", tags=["Agent Chat"])

@app.get("/")
async def root():
    return {"message": "Welcome to the MCP Chat Extension Backend!"}

# To run the backend (from mcp-chat-extension/backend_py directory):
# Make sure anp_open_sdk is in PYTHONPATH if not installed
# Example: export PYTHONPATH=$PYTHONPATH:$(pwd)/..
# Then: uvicorn app.main:app --reload --port 8000