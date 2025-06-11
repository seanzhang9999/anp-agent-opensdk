import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..core.config import USERS_CREDENTIALS_FILE, get_anp_user_base_path
from ..models.schemas import UserCreate
from anp_open_sdk.anp_sdk_user_data import (
    did_create_user,
    get_user_dir_did_doc_by_did,
    LocalUserDataManager)




USER_DATA_MANAGER = LocalUserDataManager(user_dir=str(get_anp_user_base_path()))

def load_user_credentials() -> Dict:
    if not USERS_CREDENTIALS_FILE.exists():
        return {}
    with open(USERS_CREDENTIALS_FILE, 'r') as f:
        return json.load(f)

def save_user_credentials(credentials: Dict):
    with open(USERS_CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)

def get_user_by_username(username: str) -> Optional[Dict]:
    credentials = load_user_credentials()
    return credentials.get(username)

def verify_password(plain_password: str, stored_password_data: Dict) -> bool:
    return plain_password == stored_password_data.get("password")

def create_user_with_anp(user_data: UserCreate) -> Tuple[Optional[str], Optional[str]]:
    credentials = load_user_credentials()
    if user_data.username in credentials:
        return None, "Username already exists."

    anp_user_params = {
        'name': user_data.anp_user_name or user_data.username,
        'host': user_data.anp_host,
        'port': user_data.anp_port,
        'dir': user_data.anp_dir,
        'type': user_data.anp_type
    }

    try:
        did_document = did_create_user(anp_user_params)
        if not did_document or 'id' not in did_document:
            return None, "ANP user creation failed: No DID document or ID returned."

        user_did = did_document['id']

        credentials[user_data.username] = {
            "password": user_data.password,
            "did": user_did,
            "anp_params": anp_user_params
        }
        save_user_credentials(credentials)

        USER_DATA_MANAGER.load_users()

        user_data_obj = USER_DATA_MANAGER.get_user_data(user_did)
        if not user_data_obj:
            del credentials[user_data.username]
            save_user_credentials(credentials)
            return None, f"ANP user created (DID: {user_did}), but failed to get user directory."

        user_dir_path = Path(user_data_obj.user_dir)
        personal_data_path = user_dir_path / "personal_data"
        personal_data_path.mkdir(parents=True, exist_ok=True)

        with open(personal_data_path / "welcome.txt", "w", encoding="utf-8") as wf:
            wf.write(f"Welcome, {user_data.username}! This is your personal data space.")

        return user_did, None
    except Exception as e:
        if user_data.username in credentials and credentials[user_data.username].get("did") == locals().get("user_did"):
            del credentials[user_data.username]
            save_user_credentials(credentials)
        return None, f"Error during ANP user creation or setup: {str(e)}"

def get_user_personal_data_path(username: Optional[str] = None, did: Optional[str] = None) -> Optional[Path]:
    if not username and not did:
            return None
    user_did_to_check = did
    if username and not did:
        user_info = get_user_by_username(username)
        if not user_info or "did" not in user_info:
            return None
        user_did_to_check = user_info["did"]

    if not user_did_to_check:
        return None
    
    user_data_obj = USER_DATA_MANAGER.get_user_data(user_did_to_check)
    if not user_data_obj:
        return None
    return Path(user_data_obj.user_dir) / "personal_data"
