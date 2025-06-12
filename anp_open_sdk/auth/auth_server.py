# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Authentication middleware module.
"""

import logging
from typing import Optional, Callable, Dict, Any
import fnmatch
import json
from fastapi import Request, HTTPException, Response
from fastapi.responses import JSONResponse

from .base_auth import BaseDIDAuthenticator
from .schemas import AuthenticationContext

EXEMPT_PATHS = [
    "/docs", "/anp-nlp/", "/ws/", "/publisher/agents", "/agent/group/*",
    "/redoc", "/openapi.json", "/wba/hostuser/*", "/wba/user/*", "/", "/favicon.ico",
    "/agents/example/ad.json"
]

def is_exempt(path):
    return any(fnmatch.fnmatch(path, pattern) for pattern in EXEMPT_PATHS)

def create_authenticator(auth_method: str = "wba") -> BaseDIDAuthenticator:
    if auth_method == "wba":
        from .wba_auth import WBADIDResolver, WBADIDSigner, WBAAuthHeaderBuilder, WBADIDAuthenticator, WBAAuth
        resolver = WBADIDResolver()
        signer = WBADIDSigner()
        header_builder = WBAAuthHeaderBuilder()
        wba_auth = WBAAuth()  # 新增初始化
        return WBADIDAuthenticator(resolver, signer, header_builder, wba_auth)  # 传递 wba_auth
    else:
        raise ValueError(f"Unsupported authentication method: {auth_method}")

class AgentAuthServer:
    def __init__(self, authenticator: BaseDIDAuthenticator):
        self.authenticator = authenticator

    async def verify_request(self, request: Request) -> (bool, str, Dict[str, Any]):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        req_did, target_did = self.authenticator.base_auth.extract_dids_from_auth_header(auth_header)
        context = AuthenticationContext(
            caller_did=req_did,
            target_did=target_did,
            request_url=str(request.url),
            method=request.method,
            custom_headers=dict(request.headers),
            json_data=None,
            use_two_way_auth=True,
            domain = request.url.hostname)
        try:
            success, msg = await self.authenticator.verify_response(auth_header, context)
            return success, msg, dict()
        except Exception as e:
                logging.error(f"服务端认证验证失败: {e}")
                return False, str(e), {}

async def authenticate_request(request: Request, auth_server: AgentAuthServer) -> Optional[dict]:
    if request.url.path == "/wba/auth":
        logging.info(f"安全中间件拦截/wba/auth进行认证")
        success, msg, extra = await auth_server.verify_request(request)
        if not success:
            raise HTTPException(status_code=401, detail=f"认证失败: {msg}")
        return extra
    else:
        for exempt_path in EXEMPT_PATHS:
            if exempt_path == "/" and request.url.path == "/":
                return None
            elif request.url.path == exempt_path or (exempt_path != '/' and exempt_path.endswith('/') and request.url.path.startswith(exempt_path)):
                return None
            elif is_exempt(request.url.path):
                return None
    logging.info(f"安全中间件拦截检查url:\n{request.url}")
    success, msg, extra = await auth_server.verify_request(request)
    if not success:
        raise HTTPException(status_code=401, detail=f"认证失败: {msg}")
    return extra

async def auth_middleware(request: Request, call_next: Callable, auth_method: str = "wba") -> Response:
    try:
        auth_server = AgentAuthServer(create_authenticator(auth_method))
        response_auth = await authenticate_request(request, auth_server)

        headers = dict(request.headers)
        request.state.headers = headers

        if response_auth is not None:
            response = await call_next(request)
            response.headers['authorization'] = json.dumps(response_auth) if response_auth else ""
            return response
        else:
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
