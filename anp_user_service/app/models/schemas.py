from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional

class UserCredentials(BaseModel):
    username: str
    password: str # In a real app, this would be for the raw password, then hashed

class UserCreate(UserCredentials):
    # ANP SDK specific parameters for did_create_user
    # Adjust these based on what did_create_user expects
    anp_user_name: Optional[str] = None # e.g., '智能体创建删除示范用户'
    anp_host: Optional[str] = "localhost"
    anp_port: Optional[int] = 9527 # Example port
    anp_dir: Optional[str] = "wba" # Example dir
    anp_type: Optional[str] = "user"

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    did: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[Dict[str, Any]] = None


class LLMConfig(BaseModel):
    apiBase: HttpUrl
    apiKey: str
    model: str

class ChatAgentRequest(BaseModel):
    username: Optional[str] = None # Either username or did should be provided
    did: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    success: bool
    reply: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None