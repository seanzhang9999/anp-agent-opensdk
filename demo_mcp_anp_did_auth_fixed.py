#!/usr/bin/env python3
"""
MCP + ANP DID 认证演示 - 修复版本
修复了服务启动和连接超时问题
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
import threading
from contextlib import asynccontextmanager

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
# 2. 简化的DID Provider实现（避免ANP SDK复杂性）
# ============================================================================

class SimpleDIDProvider(DidProvider):
    """简化的DID Provider实现，用于演示"""
    
    def __init__(self, did_id: str = "did:example:demo123"):
        self.did_id = did_id
        self.private_key = self._generate_key()
        
    def _generate_key(self) -> str:
        """生成简单的密钥（实际应该用真正的密钥生成算法）"""
        return hashlib.sha256(self.did_id.encode()).hexdigest()
    
    async def get_did(self) -> str:
        """返回DID"""
        return self.did_id
    
    async def sign(self, payload: str) -> str:
        """签名"""
        timestamp = int(time.time())
        signature = hmac.new(
            self.private_key.encode(),
            f"{payload}:{timestamp}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        jws = {
            "payload": payload,
            "signature": signature,
            "did": self.did_id,
            "timestamp": timestamp
        }
        
        return json.dumps(jws)
    
    async def verify(self, payload: str, signature: str, did: str) -> bool:
        """验证签名"""
        try:
            jws_data = json.loads(signature)
            
            # 验证时间戳（5分钟有效期）
            timestamp = jws_data.get("timestamp", 0)
            if time.time() - timestamp > 300:
                return False
            
            # 验证DID
            if jws_data.get("did") != did:
                return False
            
            # 验证签名
            expected_signature = hmac.new(
                self.private_key.encode(),
                f"{payload}:{timestamp}".encode(),
                hashlib.sha256
            ).hexdigest()
            
            return jws_data.get("signature") == expected_signature
            
        except Exception as e:
            logger.error(f"签名验证失败: {e}")
            return False


# ============================================================================
# 3. 外部DID Provider实现
# ============================================================================

class ExternalDidProvider(DidProvider):
    """通过HTTP调用外部DID-Agent的Provider"""
    
    def __init__(self, agent_url: str = "http://localhost:9511"):
        self.agent_url = agent_url
        self._cached_did: Optional[str] = None
        self.timeout = 10.0  # 10秒超时
    
    async def get_did(self) -> str:
        """从DID-Agent获取DID"""
        if self._cached_did:
            return self._cached_did
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
        self.did_provider = SimpleDIDProvider("did:example:shared_agent")
        self.app = self._create_app()
        self.server = None
        
    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(title="DID-Agent Service")
        
        @app.get("/")
        async def root():
            return {"service": "DID-Agent", "status": "running"}
        
        @app.get("/did")
        async def get_did():
            """获取DID"""
            did = await self.did_provider.get_did()
            logger.info(f"返回DID: {did}")
            return {"did": did}
        
        @app.post("/sign")
        async def sign_payload(request: dict):
            """签名payload"""
            payload = request.get("payload")
            if not payload:
                raise HTTPException(400, "Missing payload")
            
            jws = await self.did_provider.sign(payload)
            logger.info(f"签名请求完成")
            return {"jws": jws}
        
        @app.post("/verify")
        async def verify_signature(request: dict):
            """验证签名"""
            payload = request.get("payload")
            signature = request.get("signature")
            did = request.get("did")
            
            if not all([payload, signature, did]):
                raise HTTPException(400, "Missing required fields")
            
            valid = await self.did_provider.verify(payload, signature, did)
            logger.info(f"签名验证结果: {valid}")
            return {"valid": valid}
        
        @app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "service": "DID-Agent"}
        
        return app


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
        self.did_provider = did_provider
        self.security = HTTPBearer()
        self.app = self._create_app()
        self.server = None
    
    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(title="MCP Server with DID Auth")
        
        @app.get("/")
        async def root():
            return {"service": "MCP Server", "auth": "DID", "status": "running"}
        
        @app.post("/mcp/rpc")
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
        
        @app.get("/mcp/capabilities")
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
                    "description": "使用DID进行身份认证"
                }
            }
        
        return app
    
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
        self.timeout = 30.0  # 30秒超时
    
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
# 7. 服务管理器
# ============================================================================

class ServiceManager:
    """服务管理器，处理服务的启动和停止"""
    
    def __init__(self):
        self.did_agent_process = None
        self.mcp_server_process = None
        
    async def start_did_agent(self, port: int = 9511) -> bool:
        """启动DID-Agent服务"""
        try:
            logger.info(f"启动DID-Agent服务 (端口 {port})...")
            
            # 检查端口是否可用
            if not await self._check_port_available("localhost", port):
                logger.warning(f"端口 {port} 已被占用，尝试其他端口...")
                port = await self._find_available_port(port)
            
            did_agent = DIDAgentService()
            
            config = uvicorn.Config(
                did_agent.app,
                host="localhost",
                port=port,
                log_level="error",  # 减少日志输出
                access_log=False
            )
            
            server = uvicorn.Server(config)
            
            # 在新线程中启动服务
            def run_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(server.serve())
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            
            # 等待服务启动
            for i in range(30):  # 最多等待30秒
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        response = await client.get(f"http://localhost:{port}/health")
                        if response.status_code == 200:
                            logger.info(f"DID-Agent服务启动成功 (端口 {port})")
                            return True
                except:
                    pass
                await asyncio.sleep(1)
            
            logger.error("DID-Agent服务启动失败")
            return False
            
        except Exception as e:
            logger.error(f"启动DID-Agent服务时发生错误: {e}")
            return False
    
    async def start_mcp_server(self, did_agent_url: str, port: int = 8000) -> bool:
        """启动MCP服务"""
        try:
            logger.info(f"启动MCP服务 (端口 {port})...")
            
            # 检查端口是否可用
            if not await self._check_port_available("localhost", port):
                logger.warning(f"端口 {port} 已被占用，尝试其他端口...")
                port = await self._find_available_port(port)
            
            # 使用外部DID Provider
            did_provider = ExternalDidProvider(did_agent_url)
            mcp_server = MCPServerWithDID(did_provider)
            
            config = uvicorn.Config(
                mcp_server.app,
                host="localhost",
                port=port,
                log_level="error",  # 减少日志输出
                access_log=False
            )
            
            server = uvicorn.Server(config)
            
            # 在新线程中启动服务
            def run_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(server.serve())
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            
            # 等待服务启动
            for i in range(30):  # 最多等待30秒
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        response = await client.get(f"http://localhost:{port}/mcp/capabilities")
                        if response.status_code == 200:
                            logger.info(f"MCP服务启动成功 (端口 {port})")
                            return True
                except:
                    pass
                await asyncio.sleep(1)
            
            logger.error("MCP服务启动失败")
            return False
            
        except Exception as e:
            logger.error(f"启动MCP服务时发生错误: {e}")
            return False
    
    async def _check_port_available(self, host: str, port: int) -> bool:
        """检查端口是否可用"""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.get(f"http://{host}:{port}")
                return False  # 端口被占用
        except:
            return True  # 端口可用
    
    async def _find_available_port(self, start_port: int) -> int:
        """查找可用端口"""
        for port in range(start_port, start_port + 100):
            if await self._check_port_available("localhost", port):
                return port
        raise Exception("找不到可用端口")


# ============================================================================
# 8. 演示函数
# ============================================================================

async def demo_mcp_client(mcp_server_url: str, did_agent_url: str):
    """演示MCP客户端调用"""
    logger.info("=== MCP客户端演示开始 ===")
    
    # 创建客户端（使用外部DID Provider）
    did_provider = ExternalDidProvider(did_agent_url)
    client = MCPClientWithDID(mcp_server_url, did_provider)
    
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
        
        return True
        
    except Exception as e:
        logger.error(f"客户端演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def demo_multiple_clients(mcp_server_url: str, did_agent_url: str):
    """演示多个客户端共享同一个DID"""
    logger.info("\n=== 多客户端共享DID演示 ===")
    
    try:
        # 创建多个客户端实例
        clients = []
        for i in range(3):
            did_provider = ExternalDidProvider(did_agent_url)
            client = MCPClientWithDID(mcp_server_url, did_provider)
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
        
        return True
        
    except Exception as e:
        logger.error(f"多客户端演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main_demo():
    """主演示函数"""
    logger.info("=== MCP + DID 认证演示开始 ===")
    
    service_manager = ServiceManager()
    
    try:
        # 步骤1: 启动DID-Agent服务
        logger.info("步骤1: 启动DID-Agent服务")
        did_agent_success = await service_manager.start_did_agent(9511)
        if not did_agent_success:
            logger.error("DID-Agent服务启动失败，退出演示")
            return
        
        did_agent_url = "http://localhost:9511"
        
        # 步骤2: 启动MCP服务
        logger.info("步骤2: 启动MCP服务")
        mcp_server_success = await service_manager.start_mcp_server(did_agent_url, 8000)
        if not mcp_server_success:
            logger.error("MCP服务启动失败，退出演示")
            return
        
        mcp_server_url = "http://localhost:8000"
        
        # 额外等待确保服务完全就绪
        logger.info("等待服务完全就绪...")
        await asyncio.sleep(3)
        
        # 步骤3: 演示客户端调用
        logger.info("步骤3: 演示MCP客户端调用")
        client_success = await demo_mcp_client(mcp_server_url, did_agent_url)
        
        if client_success:
            # 步骤4: 演示多客户端
            logger.info("步骤4: 演示多客户端共享DID")
            multi_client_success = await demo_multiple_clients(mcp_server_url, did_agent_url)
            
            if multi_client_success:
                logger.info("\n=== 演示完成 ===")
                logger.info("✅ 成功验证了以下功能:")
                logger.info("1. DID-Agent统一管理DID密钥")
                logger.info("2. MCP客户端透明使用DID认证")
                logger.info("3. MCP服务器验证DID签名")
                logger.info("4. 多个客户端共享同一套DID")
                logger.info("5. 对上层业务完全透明")
            else:
                logger.error("多客户端演示失败")
        else:
            logger.error("客户端演示失败")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        logger.info("演示结束，服务将继续运行...")
        logger.info("你可以手动测试以下URL:")
        logger.info("- DID-Agent: http://localhost:9511/health")
        logger.info("- MCP Server: http://localhost:8000/mcp/capabilities")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main_demo())