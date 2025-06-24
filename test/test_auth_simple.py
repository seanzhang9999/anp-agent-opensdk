#!/usr/bin/env python3
"""
简化的认证模块测试

测试当前认证功能是否正常工作
"""

import sys
import asyncio
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 初始化配置
from anp_open_sdk.config.unified_config import UnifiedConfig, set_global_config

# 设置应用根目录为项目根目录
app_root = str(Path(__file__).parent.parent)
config = UnifiedConfig(app_root=app_root)
set_global_config(config)

from anp_open_sdk.auth.schemas import DIDCredentials, DIDDocument, DIDKeyPair, AuthenticationContext
from anp_open_sdk.auth.auth_client import create_authenticator
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager, did_create_user
from anp_open_sdk.anp_sdk_agent import LocalAgent

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_user_creation():
    """测试用户创建"""
    logger.info("=== 测试用户创建 ===")
    
    config = {
        'name': 'test_auth_user',
        'host': 'localhost',
        'port': 9527,
        'dir': 'test',
        'type': 'agent'
    }
    
    did_doc = did_create_user(config)
    if did_doc:
        logger.info(f"✅ 用户创建成功: {did_doc['id']}")
        return did_doc['id']
    else:
        logger.error("❌ 用户创建失败")
        return None

def test_user_data_loading(did):
    """测试用户数据加载"""
    logger.info("=== 测试用户数据加载 ===")
    
    user_data_manager = LocalUserDataManager()
    user_data = user_data_manager.get_user_data(did)
    
    if user_data:
        logger.info(f"✅ 用户数据加载成功")
        logger.info(f"  DID: {user_data.did}")
        logger.info(f"  名称: {user_data.name}")
        logger.info(f"  DID文档路径: {user_data.did_doc_path}")
        logger.info(f"  私钥路径: {user_data.did_private_key_file_path}")
        return user_data
    else:
        logger.error("❌ 用户数据加载失败")
        return None

def test_did_credentials_creation(user_data):
    """测试DID凭证创建"""
    logger.info("=== 测试DID凭证创建 ===")
    
    try:
        credentials = DIDCredentials.from_paths(
            did_document_path=user_data.did_doc_path,
            private_key_path=user_data.did_private_key_file_path
        )
        
        logger.info(f"✅ DID凭证创建成功")
        logger.info(f"  DID: {credentials.did_document.did}")
        logger.info(f"  密钥对数量: {len(credentials.key_pairs)}")
        
        # 测试密钥对获取
        key_pair = credentials.get_key_pair("key-1")
        if key_pair:
            logger.info(f"  密钥对获取成功: {key_pair.key_id}")
        else:
            logger.warning("  未找到key-1密钥对")
            
        return credentials
        
    except Exception as e:
        logger.error(f"❌ DID凭证创建失败: {e}")
        return None

def test_local_agent_creation(did):
    """测试LocalAgent创建"""
    logger.info("=== 测试LocalAgent创建 ===")
    
    try:
        agent = LocalAgent.from_did(did)
        logger.info(f"✅ LocalAgent创建成功")
        logger.info(f"  DID: {agent.id}")
        logger.info(f"  名称: {agent.name}")
        logger.info(f"  用户目录: {agent.user_dir}")
        return agent
        
    except Exception as e:
        logger.error(f"❌ LocalAgent创建失败: {e}")
        return None

async def test_auth_header_building(user_data):
    """测试认证头构建"""
    logger.info("=== 测试认证头构建 ===")
    
    try:
        # 创建认证上下文
        context = AuthenticationContext(
            caller_did=user_data.did,
            target_did="did:wba:example.com:test:agent",
            request_url="http://example.com/test",
            method="GET",
            use_two_way_auth=True
        )
        
        # 创建凭证
        credentials = DIDCredentials.from_paths(
            did_document_path=user_data.did_doc_path,
            private_key_path=user_data.did_private_key_file_path
        )
        
        # 创建认证器并构建认证头
        authenticator = create_authenticator("wba")
        auth_headers = authenticator.header_builder.build_auth_header(context, credentials)
        
        logger.info(f"✅ 认证头构建成功")
        logger.info(f"  认证头键数量: {len(auth_headers)}")
        if "Authorization" in auth_headers:
            logger.info(f"  包含Authorization头")
        
        return auth_headers
        
    except Exception as e:
        logger.error(f"❌ 认证头构建失败: {e}")
        return None

async def run_all_tests():
    """运行所有测试"""
    logger.info("🚀 开始认证模块基础功能测试")
    logger.info("=" * 50)
    
    # 1. 测试用户创建
    did = test_user_creation()
    if not did:
        return False
    
    # 2. 测试用户数据加载
    user_data = test_user_data_loading(did)
    if not user_data:
        return False
    
    # 3. 测试DID凭证创建
    credentials = test_did_credentials_creation(user_data)
    if not credentials:
        return False
    
    # 4. 测试LocalAgent创建
    agent = test_local_agent_creation(did)
    if not agent:
        return False
    
    # 5. 测试认证头构建
    auth_headers = await test_auth_header_building(user_data)
    if not auth_headers:
        return False
    
    logger.info("=" * 50)
    logger.info("🎉 所有基础测试通过！")
    return True

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
