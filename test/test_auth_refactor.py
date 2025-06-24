#!/usr/bin/env python3
"""
认证模块重构测试

测试从文件路径操作到内存数据操作的重构前后功能一致性
"""

import sys
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
except ImportError:
    pytest = None

from anp_open_sdk.auth.schemas import DIDCredentials, DIDDocument, DIDKeyPair, AuthenticationContext
from anp_open_sdk.auth.auth_client import AgentAuthManager, create_authenticator, agent_auth_request
from anp_open_sdk.auth.auth_server import AgentAuthServer, generate_auth_response
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager, did_create_user
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.anp_sdk import ANPSDK

logger = logging.getLogger(__name__)

class TestAuthRefactor:
    """认证重构测试类"""
    
    @classmethod
    def setup_class(cls):
        """设置测试环境"""
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_users = []
        cls.sdk = None
        
    @classmethod
    def teardown_class(cls):
        """清理测试环境"""
        if cls.temp_dir and Path(cls.temp_dir).exists():
            shutil.rmtree(cls.temp_dir)
    
    def setup_method(self):
        """每个测试方法前的设置"""
        # 创建测试用户
        self.create_test_users()
        
    def create_test_users(self):
        """创建测试用户"""
        users_config = [
            {
                'name': 'test_user_1',
                'host': 'localhost',
                'port': 9527,
                'dir': 'test',
                'type': 'agent'
            },
            {
                'name': 'test_user_2', 
                'host': 'localhost',
                'port': 9528,
                'dir': 'test',
                'type': 'agent'
            }
        ]
        
        for config in users_config:
            did_doc = did_create_user(config)
            if did_doc:
                self.test_users.append(did_doc['id'])
                logger.info(f"创建测试用户: {did_doc['id']}")
    
    def test_did_credentials_from_paths(self):
        """测试从文件路径创建DID凭证"""
        if not self.test_users:
            pytest.skip("没有可用的测试用户")
            
        user_data_manager = LocalUserDataManager()
        user_data = user_data_manager.get_user_data(self.test_users[0])
        
        # 测试从文件路径创建凭证
        credentials = DIDCredentials.from_paths(
            did_document_path=user_data.did_doc_path,
            private_key_path=user_data.did_private_key_file_path
        )
        
        assert credentials is not None
        assert credentials.did_document is not None
        assert credentials.did_document.did == self.test_users[0]
        assert len(credentials.key_pairs) > 0
        
        logger.info("✅ DID凭证从文件路径创建测试通过")
    
    def test_did_credentials_memory_operations(self):
        """测试DID凭证的内存操作"""
        if not self.test_users:
            pytest.skip("没有可用的测试用户")
            
        user_data_manager = LocalUserDataManager()
        user_data = user_data_manager.get_user_data(self.test_users[0])
        
        # 从文件创建凭证
        credentials = DIDCredentials.from_paths(
            did_document_path=user_data.did_doc_path,
            private_key_path=user_data.did_private_key_file_path
        )
        
        # 测试内存操作
        key_pair = credentials.get_key_pair("key-1")
        assert key_pair is not None
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None
        
        # 测试添加新密钥对
        new_key_pair = DIDKeyPair.from_file_path(
            user_data.did_private_key_file_path, "test-key"
        )
        credentials.add_key_pair(new_key_pair)
        
        retrieved_key = credentials.get_key_pair("test-key")
        assert retrieved_key is not None
        assert retrieved_key.key_id == "test-key"
        
        logger.info("✅ DID凭证内存操作测试通过")
    
    async def test_auth_header_building(self):
        """测试认证头构建"""
        if len(self.test_users) < 2:
            pytest.skip("需要至少2个测试用户")
            
        user_data_manager = LocalUserDataManager()
        caller_data = user_data_manager.get_user_data(self.test_users[0])
        target_did = self.test_users[1]
        
        # 创建认证上下文
        context = AuthenticationContext(
            caller_did=caller_data.did,
            target_did=target_did,
            request_url="http://localhost:9528/test",
            method="GET",
            use_two_way_auth=True
        )
        
        # 创建凭证
        credentials = DIDCredentials.from_paths(
            did_document_path=caller_data.did_doc_path,
            private_key_path=caller_data.did_private_key_file_path
        )
        
        # 测试认证头构建
        authenticator = create_authenticator("wba")
        auth_headers = authenticator.header_builder.build_auth_header(context, credentials)
        
        assert auth_headers is not None
        assert "Authorization" in auth_headers
        
        logger.info("✅ 认证头构建测试通过")
    
    async def test_authentication_flow(self):
        """测试完整的认证流程"""
        if len(self.test_users) < 2:
            pytest.skip("需要至少2个测试用户")
            
        # 启动SDK服务器
        sdk = ANPSDK(host="localhost", port=9527)
        
        # 创建智能体
        agent1 = LocalAgent.from_did(self.test_users[0])
        agent2 = LocalAgent.from_did(self.test_users[1])
        
        # 注册API处理器
        @agent2.expose_api("/test")
        async def test_api(request_data, request):
            return {"status": "success", "message": "API调用成功"}
        
        # 注册智能体
        sdk.register_agent(agent1)
        sdk.register_agent(agent2)
        
        # 启动服务器（在后台）
        import threading
        server_thread = threading.Thread(target=sdk.start_server, daemon=True)
        server_thread.start()
        
        # 等待服务器启动
        await asyncio.sleep(2)
        
        try:
            # 测试认证请求
            status, response_data, message, success = await agent_auth_request(
                caller_agent=agent1.id,
                target_agent=agent2.id,
                request_url=f"http://localhost:9527/agent/api/{agent2.id}/test",
                method="GET",
                use_two_way_auth=True
            )
            
            assert success, f"认证失败: {message}"
            assert status == 200, f"HTTP状态码错误: {status}"
            
            logger.info("✅ 完整认证流程测试通过")
            
        finally:
            # 清理
            if hasattr(sdk, 'stop_server'):
                sdk.stop_server()
    
    async def test_token_operations(self):
        """测试令牌操作"""
        if not self.test_users:
            pytest.skip("没有可用的测试用户")
            
        agent = LocalAgent.from_did(self.test_users[0])
        remote_did = "did:wba:example.com:agent:test"
        
        # 测试存储令牌
        test_token = "test_token_12345"
        agent.contact_manager.store_token_from_remote(remote_did, test_token)
        
        # 测试获取令牌
        stored_token = agent.contact_manager.get_token_from_remote(remote_did)
        assert stored_token is not None
        assert stored_token["token"] == test_token
        
        # 测试撤销令牌
        agent.contact_manager.revoke_token_to_remote(remote_did)
        
        logger.info("✅ 令牌操作测试通过")
    
    def test_contact_management(self):
        """测试联系人管理"""
        if not self.test_users:
            pytest.skip("没有可用的测试用户")
            
        agent = LocalAgent.from_did(self.test_users[0])
        
        # 测试添加联系人
        contact = {
            "did": "did:wba:example.com:agent:contact",
            "name": "测试联系人",
            "host": "example.com",
            "port": 80
        }
        
        agent.add_contact(contact)
        
        # 测试获取联系人
        retrieved_contact = agent.get_contact(contact["did"])
        assert retrieved_contact is not None
        assert retrieved_contact["name"] == contact["name"]
        
        # 测试列出所有联系人
        contacts = agent.list_contacts()
        assert len(contacts) > 0
        assert any(c["did"] == contact["did"] for c in contacts)
        
        logger.info("✅ 联系人管理测试通过")
    
    async def test_memory_vs_file_consistency(self):
        """测试内存操作与文件操作的一致性"""
        if not self.test_users:
            pytest.skip("没有可用的测试用户")
            
        user_data_manager = LocalUserDataManager()
        user_data = user_data_manager.get_user_data(self.test_users[0])
        
        # 从文件创建凭证
        file_credentials = DIDCredentials.from_paths(
            did_document_path=user_data.did_doc_path,
            private_key_path=user_data.did_private_key_file_path
        )
        
        # 验证DID文档一致性
        assert file_credentials.did_document.did == user_data.did
        
        # 验证密钥对一致性
        key_pair = file_credentials.get_key_pair("key-1")
        assert key_pair is not None
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None
        
        logger.info("✅ 内存与文件操作一致性测试通过")

def run_auth_tests():
    """运行所有认证测试"""
    import pytest
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行测试
    test_file = __file__
    pytest.main([test_file, "-v", "-s"])

async def run_async_tests():
    """运行异步测试"""
    test_instance = TestAuthRefactor()
    test_instance.setup_class()
    
    try:
        test_instance.setup_method()
        
        # 运行同步测试
        test_instance.test_did_credentials_from_paths()
        test_instance.test_did_credentials_memory_operations()
        test_instance.test_contact_management()
        
        # 运行异步测试
        await test_instance.test_auth_header_building()
        await test_instance.test_authentication_flow()
        await test_instance.test_token_operations()
        await test_instance.test_memory_vs_file_consistency()
        
        logger.info("🎉 所有认证测试通过！")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        raise
    finally:
        test_instance.teardown_class()

if __name__ == "__main__":
    # 可以选择运行pytest或直接运行异步测试
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--pytest":
        run_auth_tests()
    else:
        asyncio.run(run_async_tests())
