"""
Authentication middleware module.
"""
import logging
from typing import List, Optional, Callable
from fastapi import Request, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic_core.core_schema import none_schema
from anp_core.auth.did_auth import handle_did_auth, get_and_validate_domain
from anp_core.auth.token_auth import handle_bearer_auth
import json
import fnmatch
# from anp_sdk import ANPSDK

# Define exempt paths that don't require authentication

EXEMPT_PATHS = [
    "/docs",
    "/anp-nlp/",
    "/ws/",
    "/group/*",
    "/redoc", 
    "/openapi.json",
    "/wba/user/*",  # Allow access to DID documents
    "/",           # Allow access to root endpoint
    "/agents/example/ad.json"  # Allow access to agent description
]  # "/wba/test" path removed from exempt list, now requires authentication


async def verify_auth_header(request: Request , sdk = None) -> dict:
    """
    Verify authentication header and return authenticated user data.
    
    Args:
        request: FastAPI request object
        
    Returns:
        dict: Authenticated user data
        
    Raises:
        HTTPException: When authentication fails
    """
    from anp_sdk import ANPSDK
    from anp_core.auth.did_auth import handle_did_auth, get_and_validate_domain
    # Get authorization header
    auth_header = request.headers.get("Authorization")

    req_did = request.headers.get("req_did")
    resp_did = request.headers.get("resp_did")
    if not req_did or not resp_did:
        req_did = request.query_params.get("req_did", "demo_caller")
        resp_did = request.query_params.get("resp_did", "demo_responser")
        if not req_did or not resp_did:
            raise HTTPException(status_code=401, detail="Missing req_did or resp_did in headers or query parameters")
    # Check if authorization header is present

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    # Handle DID WBA authentication
    if not auth_header.startswith("Bearer "):
        domain = get_and_validate_domain(request)
        result = await handle_did_auth(auth_header, domain,request , sdk)
        return result
    
    # Handle Bearer token authentication
    
    return await handle_bearer_auth(auth_header,req_did,resp_did , sdk)

def is_exempt(path):
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXEMPT_PATHS)

async def authenticate_request(request: Request , sdk= None) -> Optional[dict]:
    """
    Authenticate a request and return user data if successful.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Optional[dict]: Authenticated user data or None for exempt paths
        
    Raises:
        HTTPException: When authentication fails
    """
    # Log request path and headers for debugging

    
    # 特别检查 /wba/test 路径，确保它不被视为免认证
    if request.url.path == "/wba/auth":
        logging.info(f"安全中间件拦截/wba/auth进行did认证兼token颁发或token校验")
        result = await verify_auth_header(request,sdk)
        return result
    else:
        for exempt_path in EXEMPT_PATHS:
            # logging.info(f"Checking if {request.url.path} matches exempt path {exempt_path}")
            # 特殊处理根路径"/"，它只应该精确匹配
            if exempt_path == "/":
                if request.url.path == "/":
            #        logging.info(f"Path {request.url.path} is exempt from authentication (matched root path)")
                    return None
            # 其他路径的匹配逻辑
            elif request.url.path == exempt_path or (exempt_path.endswith('/') and request.url.path.startswith(exempt_path)):
                return None
            elif is_exempt(request.url.path):
            #    logging.info(f"Path {request.url.path} is exempt from authentication (matched {exempt_path})")
                return None
    
    logging.info(f"安全中间件拦截检查url:\n{request.url}")
    result = await verify_auth_header(request , sdk)
    return result


async def auth_middleware(request: Request, call_next: Callable, sdk = None) -> Response:
    """
    Authentication middleware for FastAPI.
    
    Args:
        request: FastAPI request object
        call_next: Next middleware or endpoint handler
        
    Returns:
        Response: API response
    """
    try:
        # Add user data to request state if authenticated
        response_auth = await authenticate_request(request,sdk)

        headers = dict(request.headers) # 读取请求头
        request.state.headers = headers  # 存储在 request.state

        if response_auth is not None:
            response = await call_next(request)
            if isinstance(response_auth, str):
                response.headers['authorization'] = response_auth
                return response
            else:
                response.headers['authorization'] = json.dumps(response_auth[0])
                return response
            # for key, value in response_auth[0].items():
            #     if isinstance(value, dict):  
            #         response.headers[key] = json.dumps(value, separators=(",", ":"))  # ✅ 转换为 JSON 字符串
            #    else:
            #        response.headers[key] = str(value)
            # response.headers["authorization"] = str("ABC")

        else:
        #    logging.info("Authentication skipped for exempt path")
            return await call_next(request)


    
    except HTTPException as exc:
        logging.error(f"Authentication error: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    except Exception as e:
        logging.error(f"Unexpected error in auth middleware: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )
