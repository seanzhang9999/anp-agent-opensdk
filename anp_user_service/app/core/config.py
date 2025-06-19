import os
from pathlib import Path
from anp_open_sdk.config import config
# Base directory of the backend_py package
BACKEND_BASE_DIR = Path(__file__).resolve().parent.parent.parent
USERS_CREDENTIALS_FILE = BACKEND_BASE_DIR / "users_credentials.json"

# ANP SDK related configurations - these might come from .env or anp_open_sdk's own config
# This is a placeholder; you'll need to ensure anp_open_sdk.config.dynamic_config is loaded correctly.
# For example, if anp_open_sdk relies on a .env file in the project root:
from dotenv import load_dotenv
load_dotenv(dotenv_path=BACKEND_BASE_DIR.parent / '.env') # Assumes .env is in mcp-chat-extension root

# Attempt to import ANP SDK components. This relies on PYTHONPATH being set correctly.
try:
    from anp_open_sdk.config.legacy.dynamic_config import dynamic_config
    ANP_USER_DID_PATH_KEY = 'anp_user_service.user_did_path' # The key used in your ANP SDK's config
    # Example: ANP_USER_BASE_PATH = Path(dynamic_config.get(ANP_USER_DID_PATH_KEY))
except ImportError:
    logger.debug("Warning: ANP SDK dynamic_config could not be imported. Paths may not be resolved correctly.")
    dynamic_config = None
    # ANP_USER_BASE_PATH = BACKEND_BASE_DIR.parent / "wba" / "user" # Fallback or example

# This function tries to get the user base path from ANP SDK's dynamic config
def get_anp_user_base_path() -> Path:
    if dynamic_config:
        path_str = dynamic_config.get(ANP_USER_DID_PATH_KEY)
        if path_str:
            return Path(path_str)
    logger.debug(f"Warning: Could not get '{ANP_USER_DID_PATH_KEY}' from dynamic_config. Using fallback.")
    return BACKEND_BASE_DIR / "anp_users"



# LLM Configuration (defaults, can be overridden by extension)
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gpt-3.5-turbo")