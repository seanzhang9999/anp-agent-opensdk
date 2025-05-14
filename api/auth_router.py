"""
Authentication API router.
"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Request, Header, HTTPException, Depends

from anp_core.auth.did_auth import get_and_validate_domain, handle_did_auth
from anp_core.auth.token_auth import handle_bearer_auth
import json

router = APIRouter(tags=["authentication"])


@router.post("/auth/did-wba", summary="Authenticate using DID WBA")
async def did_wba_auth(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Dict:
    """
    Authenticate using DID WBA method.
    
    Args:
        request: FastAPI request object
        authorization: DID WBA authorization header
        
    Returns:
        Dict: Authentication result with token
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    # Get and validate domain
    domain = get_and_validate_domain(request)
    
    # Process DID WBA authentication
    return await handle_did_auth(authorization, domain,request)


@router.get("/auth/verify", summary="Verify bearer token")
async def verify_token(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Dict:
    """
    Verify JWT bearer token.
    
    Args:
        request: FastAPI request object
        authorization: Bearer token header
        
    Returns:
        Dict: Token verification result
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format, must use Bearer scheme")
    
    # Verify bearer token
    user_data = await handle_bearer_auth(authorization)
    
    return {
        "verified": True,
        "did": user_data["did"],
        "message": "Token verified successfully"
    }


@router.get("/wba/test", summary="Test endpoint for DID WBA authentication")
async def test_endpoint(request: Request) -> Dict:
    """
    Test endpoint for DID WBA authentication.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dict: Test result
    """
    # Try to get JSON data if available
    user = None

    RequestDID = request.state.headers.get("tokenrequestdid", "")


    try:
        if RequestDID != "": # token 用户
            user = RequestDID
        else: # did 用户   
            auth_data = request.state.headers.get("authorization", "")
                # 检查auth_data是否为字符串
            if isinstance(auth_data, str) and " " in auth_data:
                auth_data = auth_data.split(" ", 1)[1]
                auth_dict =parse_auth_str_to_dict(auth_data)
                user = auth_dict.get("did")

    except Exception as e:
        logging.warning(f"解析认证数据时出错: {e}")
        user = None
    
    logging.info(f"Received test request with user: {user}")

    if not user:
        return {
            "status": "warning",
            "message": "No authentication provided, but access allowed"
        }
    
    return{
         "status": "success",
         "message": "Successfully authenticated",
         "RquestUser": user,
         "authenticated": True
    }
    
    

def parse_auth_str_to_dict(auth_str: str) -> dict:
    """
    将类似于 'key1="value1", key2="value2"' 的字符串解析为字典
    """
    result = {}
    try:
        # 先按逗号分割，再按等号分割
        for kv in auth_str.split(", "):
            if "=" in kv:
                k, v = kv.split("=", 1)
                result[k.strip()] = v.strip('"')
    except Exception as e:
        logging.warning(f"解析认证字符串为字典时出错: {e}")
    return result
    
    
