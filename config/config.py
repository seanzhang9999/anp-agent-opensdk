"""
DID WBA configuration module with both client and server functionalities.
"""
import os
import secrets
from typing import List, Dict, Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parents[1] / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """DID WBA configuration settings."""
    
    # Server settings
    HOST: str = os.getenv("HOST", "localhost")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # JWT settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "default_jwt_secret_key_please_change")
    # JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "RS256")  # Changed to RS256 for asymmetric keys
    JWT_ALGORITHM: str =  "RS256" # Changed to RS256
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_PRIVATE_KEY_PATH: str = os.getenv("JWT_PRIVATE_KEY_PATH", os.path.join(Path(__file__).parents[1], "doc/test_jwt_key/private_key.pem"))
    JWT_PUBLIC_KEY_PATH: str = os.getenv("JWT_PUBLIC_KEY_PATH", os.path.join(Path(__file__).parents[1], "doc/test_jwt_key/public_key.pem"))
    
    # DID settings
    DID_DOCUMENTS_PATH: str = os.getenv("DID_DOCUMENTS_PATH", "did_keys")
    DID_DOCUMENT_FILENAME: str = "did.json"
    PRIVATE_KEY_FILENAME: str = "key-1_private.pem"
    
    # Target server settings (for client requests)
    TARGET_SERVER_HOST: str = os.getenv("TARGET_SERVER_HOST", "localhost")
    TARGET_SERVER_PORT: int = int(os.getenv("TARGET_SERVER_PORT", "8000"))
    
    # WBA settings
    @property
    def WBA_SERVER_DOMAINS(self) -> List[str]:
        """Get WBA server domains as a list from comma-separated string."""
        domains_str = os.getenv("WBA_SERVER_DOMAINS", "localhost:8000")
        return [domain.strip() for domain in domains_str.split(",")]
    
    # Constants
    NONCE_EXPIRATION_MINUTES: int = 6
    TIMESTAMP_EXPIRATION_MINUTES: int = 5
    MAX_JSON_SIZE: int = 2048  # 2KB
    
    class Config:
        """Pydantic configuration class."""
        case_sensitive = True


settings = Settings()
