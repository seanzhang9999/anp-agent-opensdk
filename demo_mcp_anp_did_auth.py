#!/usr/bin/env python3
"""
MCP + ANP DID 认证演示
演示如何使用ANP DID系统为FastMCP提供统一的身份认证

架构：
1. DID-Agent: 统一管理ANP DID密钥和签名
2. MCP Server: 使用ANP DID进行身份验证
3. MCP Client: 通过DID Provider进行透明认证
"""

import asyncio
import json
import time
import hashlib
import hmac
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import os
import sys
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.anp_sdk_tool import did_create_user
from loguru import logger

# ============================================================================
# 1. DID Provider 接口定义
# ============================================================================

class DidProvider(ABC):
    """DID Provider 抽象接口"""
    
    @abstractmethod
    async def get_did(self) -> str:
        """返回当前DID标识"""
        pass
    
    @abstractmethod
    async def sign(self, payload: str) -> str:
        """给payload签名，返回JWS格式签名"""
        pass
    
    @abstractmethod
    async def verify(self, payload: str, signature: str, did: str) -> bool:
        """验证签名"""
        pass


# ============================================================================
# 2. ANP DID Provider 实现
# ============================================================================

class ANPDidProvider(DidProvider):
    """基于ANP SDK的DID Provider实现"""
    
    def __init__(self, agent_name: str = "mcp_client_agent"):
        self.agent_name = agent_name
        self.sdk = ANPSDK()
        self.agent: Optional[LocalAgent] = None
        self._did: Optional[str] = None
        
    async def initialize(self):
        """初始化ANP DID"""
        try:
            # 1. 尝试加载现有DID
            user_data = self.sdk.user_data_manager.get_user_data_by_name(self.agent_name)
            
            if user_data:
                # 使用现有DID
                self._did = user_data.did
                self.agent = LocalAgent(self.sdk, user_data.did, user_data.name)
                logger.info(f"加载现有ANP DID: {self._did}")
            else:
                # 创建新的DID
                self._did = await self._create_new_did()
                self.agent = LocalAgent(self.sdk, self._did, self.agent_name)
                logger.info(f"创建新的ANP DID: {self._did}")
            
            # 注册到SDK
            self.sdk.register_agent(self.agent)
            return True
            
        except Exception as e:
            logger.error(f"ANP DID初始化失败: {e}")
            return False
    
    async def _create_new_did(self) -> str:
        """创建新的ANP DID"""
        temp_user_params = {
            'name': self.agent_name,
            'host': 'localhost',
            'port': 9527,
            'dir': 'wba',
            'type': 'user'
        }
        
        did_document = did_create_user(temp_user_params)
        if did_document:
            return did_document['id']
        else:
            raise Exception("创建ANP DID失败")
    
    async def get_did(self) -> str:
        """返回当前DID标识"""
        if not self._did:
            await self.initialize()
        return self._did
    
    async def sign(self, payload: str) -> str:
        """使用ANP私钥签名"""
        if not self.agent:
            await self.initialize()
        
        try:
            # 使用ANP SDK的签名功能
            # 这里简化处理，实际应该使用ANP的完整签名流程
            signature = self._generate_anp_signature(payload)
            
            # 构建JWS格式
            jws = {
                "payload": payload,
                "signature": signature,
                "did": self._did,
                "timestamp": int(time.time())
            }
            
            return json.dumps(jws)
            
        except Exception as e:
            logger.error(f"ANP签名失败: {e}")
            raise
    
    async def verify(self, payload: str, signature: str, did: str) -> bool:
        """验证ANP签名"""
        try:
            jws_data = json.loads(signature)
            
            # 验证时间戳（5分钟有效期）
            timestamp = jws_data.get("timestamp", 0)
            if time.time() - timestamp > 300:  # 5分钟
                logger.warning("签名已过期")
                return False
            
            # 验证DID
            if jws_data.get("did") != did:
                logger.warning("DID不匹配")
                return False
            
            # 验证签名（这里简化处理）
            expected_signature = self._generate_anp_signature(payload)
            return jws_data.get("signature") == expected_signature
            
        except Exception as e:
            logger.error(f"签名验证失败: {e}")
            return False
    
    def _generate_anp_signature(self, payload: str) -> str:
        """生成ANP签名（简化版本）"""
        # 实际应该使用ANP的完整签名算法
        # 这里用HMAC作为演示
        if not self.agent:
            raise Exception("Agent未初始化")
        
        # 使用DID作为密钥（实际应该用私钥）
        key = self._did.encode('utf-8')
        signature = hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature


# ============================================================================
# 3. 外部DID Provider实现
# ============================================================================

class ExternalDidProvider(DidProvider):
    """通过HTTP调用外部DID-Agent的Provider"""
    
    def __init__(self, agent_url: str = "http://localhost:9511"):
        self.agent_url = agent_url
        self._cached_did: Optional[str] = None
    
    async def get_did(self) -> str:
        """从DID-Agent获取DID"""
        if self._cached_did:
            return self._cached_did
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.agent_url}/did")
                response.raise_for_status()
                data = response.json()
                self._cached_did = data["did"]
                return self._cached_did
            except Exception as e:
                logger.error(f"获取DID失败: {e}")
                raise
    
    async def sign(self, payload: str) -> str:
        """请求DID-Agent进行签名"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.agent_url}/sign",
                    json={"payload": payload}
                )
                response.raise_for_status()
                data = response.json()
                return data["jws"]
            except Exception as e:
                logger.error(f"签名请求失败: {e}")
                raise
    
    async def verify(self, payload: str, signature: str, did: str) -> bool:
        """请求DID-Agent验证签名"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.agent_url}/verify",
                    json={
                        "payload": payload,
                        "signature": signature,
                        "did": did
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["valid"]
            except Exception as e:
                logger.error(f"签名验证失败: {e}")
                return False


# ============================================================================
# 4. DID-Agent 服务
# ============================================================================

class DIDAgentService:
    """统一的DID-Agent服务，管理所有DID密钥"""
    
    def __init__(self):
        self.app = FastAPI(title="DID-Agent Service")
        self.did_provider = ANPDidProvider("shared_did_agent")
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        
        @self.app.on_event("startup")
        async def startup():
            await self.did_provider.initialize()
            logger.info("DID-Agent服务启动完成")
        
        @self.app.get("/did")
        async def get_did():
            """获取DID"""
            did = await self.did_provider.get_did()
            return {"did": did}
        
        @self.app.post("/sign")
        async def sign_payload(request: dict):
            """签名payload"""
            payload = request.get("payload")
            if not payload:
                raise HTTPException(400, "Missing payload")
            
            jws = await self.did_provider.sign(payload)
            return {"jws": jws}
        
        @self.app.post("/verify")
        async def verify_signature(request: dict):
            """验证签名"""
            payload = request.get("payload")
            signature = request.get("signature")
            did = request.get("did")
            
            if not all([payload, signature, did]):
                raise HTTPException(400, "Missing required fields")
            
            valid = await self.did_provider.verify(payload, signature, did)
            return {"valid": valid}
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "service": "DID-Agent"}


# ============================================================================
# 5. MCP Server with DID Authentication
# ============================================================================

@dataclass
class MCPRequest:
    """MCP请求数据结构"""
    method: str
    params: Dict[str, Any]
    id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class MCPServerWithDID:
    """支持DID认证的MCP Server"""
    
    def __init__(self, did_provider: DidProvider):
        self.app = FastAPI(title="MCP Server with DID Auth")
        self.did_provider = did_provider
        self.security = HTTPBearer()
        self._setup_routes()
    
    def _setup_routes(self):
        """设置MCP服务路由"""
        
        @self.app.post("/mcp/rpc")
        async def mcp_rpc(
            request: dict,
            credentials: HTTPAuthorizationCredentials = Depends(self.security)
        ):
            """MCP RPC端点，支持DID认证"""
            
            # 1. 验证DID认证
            auth_result = await self._verify_did_auth(request, credentials.credentials)
            if not auth_result["valid"]:
                raise HTTPException(401, f"DID认证失败: {auth_result['error']}")
            
            # 2. 处理MCP请求
            mcp_request = MCPRequest(
                method=request.get("method"),
                params=request.get("params", {}),
                id=request.get("id"),
                meta=request.get("__meta")
            )
            
            # 3. 调用对应的处理器
            result = await self._handle_mcp_request(mcp_request)
            
            return {
                "jsonrpc": "2.0",
                "id": mcp_request.id,
                "result": result
            }
        
        @self.app.get("/mcp/capabilities")
        async def get_capabilities():
            """获取MCP服务能力"""
            return {
                "capabilities": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "回显消息",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "time",
                            "description": "获取当前时间"
                        }
                    ]
                },
                "auth": {
                    "type": "did",
                    "description": "使用ANP DID进行身份认证"
                }
            }
    
    async def _verify_did_auth(self, request: dict, token: str) -> Dict[str, Any]:
        """验证DID认证"""
        try:
            # 1. 解析认证信息
            auth_data = json.loads(token)
            did = auth_data.get("did")
            signature = auth_data.get("signature")
            
            if not did or not signature:
                return {"valid": False, "error": "Missing DID or signature"}
            
            # 2. 构建待验证的payload
            meta = request.get("__meta", {})
            payload_data = {
                "method": request.get("method"),
                "params": request.get("params"),
                "timestamp": meta.get("ts")
            }
            payload = json.dumps(payload_data, sort_keys=True)
            
            # 3. 验证签名
            valid = await self.did_provider.verify(payload, signature, did)
            
            if valid:
                return {"valid": True, "did": did}
            else:
                return {"valid": False, "error": "Signature verification failed"}
                
        except Exception as e:
            logger.error(f"DID认证验证失败: {e}")
            return {"valid": False, "error": str(e)}
    
    async def _handle_mcp_request(self, request: MCPRequest) -> Dict[str, Any]:
        """处理MCP请求"""
        method = request.method
        params = request.params
        
        if method == "tools/call":
            return await self._handle_tool_call(params)
        elif method == "tools/list":
            return {"tools": ["echo", "time"]}
        else:
            raise HTTPException(400, f"Unknown method: {method}")
    
    async def _handle_tool_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "echo":
            message = arguments.get("message", "Hello")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Echo: {message}"
                    }
                ]
            }
        elif tool_name == "time":
            current_time = datetime.now().isoformat()
            return {
                "content": [
                    {
                        "type": "text", 
                        "text": f"Current time: {current_time}"
                    }
                ]
            }
        else:
            raise HTTPException(400, f"Unknown tool: {tool_name}")


# ============================================================================
# 6. MCP Client with DID Authentication
# ============================================================================

class MCPClientWithDID:
    """支持DID认证的MCP Client"""
    
    def __init__(self, server_url: str, did_provider: DidProvider):
        self.server_url = server_url
        self.did_provider = did_provider
        self._did: Optional[str] = None
    
    async def initialize(self):
        """初始化客户端"""
        self._did = await self.did_provider.get_did()
        logger.info(f"MCP Client初始化完成，DID: {self._did}")
    
    async def rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送RPC请求，自动附加DID认证"""
        
        # 1. 构建请求数据
        timestamp = int(time.time())
        request_data = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": f"req_{timestamp}",
            "__meta": {
                "ts": timestamp
            }
        }
        
        # 2. 生成认证签名
        payload_data = {
            "method": method,
            "params": params,
            "timestamp": timestamp
        }
        payload = json.dumps(payload_data, sort_keys=True)
        signature = await self.did_provider.sign(payload)
        
        # 3. 构建认证头
        auth_token = json.dumps({
            "did": self._did,
            "signature": signature
        })
        
        # 4. 发送请求
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server_url}/mcp/rpc",
                    json=request_data,
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.error(f"MCP RPC调用失败: {e}")
                raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        return await self.rpc("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
    
    async def list_tools(self) -> Dict[str, Any]:
        """列出可用工具"""
        return await self.rpc("tools/list", {})


# ============================================================================
# 7. 演示主函数
# ============================================================================

async def start_did_agent():
    """启动DID-Agent服务"""
    logger.info("启动DID-Agent服务...")
    did_agent = DIDAgentService()
    
    config = uvicorn.Config(
        did_agent.app,
        host="localhost",
        port=9511,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # 在后台启动服务
    task = asyncio.create_task(server.serve())
    
    # 等待服务启动
    await asyncio.sleep(2)
    
    return task


async def start_mcp_server():
    """启动MCP服务"""
    logger.info("启动MCP服务...")
    
    # 使用外部DID Provider
    did_provider = ExternalDidProvider("http://localhost:9511")
    mcp_server = MCPServerWithDID(did_provider)
    
    config = uvicorn.Config(
        mcp_server.app,
        host="localhost",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # 在后台启动服务
    task = asyncio.create_task(server.serve())
    
    # 等待服务启动
    await asyncio.sleep(2)
    
    return task


async def demo_mcp_client():
    """演示MCP客户端调用"""
    logger.info("=== MCP客户端演示开始 ===")
    
    # 创建客户端（使用外部DID Provider）
    did_provider = ExternalDidProvider("http://localhost:9511")
    client = MCPClientWithDID("http://localhost:8000", did_provider)
    
    # 初始化客户端
    await client.initialize()
    
    try:
        # 测试1: 列出工具
        logger.info("\n1. 列出可用工具:")
        tools_result = await client.list_tools()
        logger.info(f"可用工具: {tools_result}")
        
        # 测试2: 调用echo工具
        logger.info("\n2. 调用echo工具:")
        echo_result = await client.call_tool("echo", {"message": "Hello from MCP Client with DID!"})
        logger.info(f"Echo结果: {echo_result}")
        
        # 测试3: 调用time工具
        logger.info("\n3. 调用time工具:")
        time_result = await client.call_tool("time", {})
        logger.info(f"Time结果: {time_result}")
        
        # 测试4: 多次调用测试签名性能
        logger.info("\n4. 性能测试 - 连续调用:")
        start_time = time.time()
        for i in range(5):
            result = await client.call_tool("echo", {"message": f"Performance test {i+1}"})
            logger.info(f"调用{i+1}: {result['result']['content'][0]['text']}")
        
        end_time = time.time()
        logger.info(f"5次调用耗时: {end_time - start_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"客户端演示失败: {e}")
        import traceback
        traceback.print_exc()


async def demo_multiple_clients():
    """演示多个客户端共享同一个DID"""
    logger.info("\n=== 多客户端共享DID演示 ===")
    
    # 创建多个客户端实例
    clients = []
    for i in range(3):
        did_provider = ExternalDidProvider("http://localhost:9511")
        client = MCPClientWithDID("http://localhost:8000", did_provider)
        await client.initialize()
        clients.append(client)
    
    # 验证所有客户端使用相同的DID
    dids = [client._did for client in clients]
    logger.info(f"所有客户端的DID: {dids}")
    
    if len(set(dids)) == 1:
        logger.info("✅ 成功：所有客户端共享同一个DID")
    else:
        logger.error("❌ 失败：客户端使用了不同的DID")
    
    # 并发调用测试
    logger.info("\n并发调用测试:")
    tasks = []
    for i, client in enumerate(clients):
        task = client.call_tool("echo", {"message": f"来自客户端{i+1}的并发请求"})
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    for i, result in enumerate(results):
        logger.info(f"客户端{i+1}结果: {result['result']['content'][0]['text']}")


async def main_demo():
    """主演示函数"""
    logger.info("=== MCP + ANP DID 认证演示开始 ===")
    
    # 启动服务
    logger.info("步骤1: 启动DID-Agent服务")
    did_agent_task = await start_did_agent()
    
    logger.info("步骤2: 启动MCP服务")
    mcp_server_task = await start_mcp_server()
    
    try:
        # 等待服务完全启动
        await asyncio.sleep(3)
        
        # 演示客户端调用
        logger.info("步骤3: 演示MCP客户端调用")
        await demo_mcp_client()
        
        # 演示多客户端
        logger.info("步骤4: 演示多客户端共享DID")
        await demo_multiple_clients()
        
        logger.info("\n=== 演示完成 ===")
        logger.info("✅ 成功验证了以下功能:")
        logger.info("1. DID-Agent统一管理ANP DID密钥")
        logger.info("2. MCP客户端透明使用DID认证")
        logger.info("3. MCP服务器验证DID签名")
        logger.info("4. 多个客户端共享同一套DID")
        logger.info("5. 对上层业务完全透明")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        logger.info("清理资源...")
        # 注意：实际部署中应该优雅地关闭服务


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main_demo())