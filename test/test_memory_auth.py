#!/usr/bin/env python3
"""
内存版本认证功能测试

测试新的内存数据操作认证功能
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

from anp_open_sdk.auth.schemas import DIDCredentials, AuthenticationContext
from anp_open_sdk.auth.memory_auth_header_builder import MemoryWBAAuthHeaderBuilder, create_memory_auth_header_client
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager, did_create_user

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_memory_credentials_creation():
    """测试内存凭证创建"""
    logger.info("=== 测试内存凭证创建 ===")
    
    # 创建测试用户
    config = {
        'name': 'test_memory_user',
        'host': 'localhost',
        'port': 9527,
        'dir': 'test',
        'type': 'agent'
    }
    
    did_doc = did_create_user(config)
    if not did_doc:
        logger.error("❌ 用户创建失败")
        return None
    
    logger.info(f"✅ 用户创建成功: {did_doc['id']}")
    
    # 获取用户数据
    user_data_manager = LocalUserDataManager()
    user_data = user_data_manager.get_user_data(did_doc['id'])
    
    if not user_data:
        logger.error("❌ 用户数据获取失败")
        return None
    
    # 测试内存凭证创建
    try:
        credentials = user_data.get_memory_credentials()
        if credentials:
            logger.info(f"✅ 内存凭证创建成功")
            logger.info(f"  DID: {credentials.did_document.did}")
            logger.info(f"  密钥对数量: {len(credentials.key_pairs)}")
            return credentials, user_data
        else:
            logger.error("❌ 内存凭证创建失败")
            return None
    except Exception as e:
        logger.error(f"❌ 内存凭证创建异常: {e}")
        return None

def test_memory_auth_header_building(credentials):
    """测试内存版本认证头构建"""
    logger.info("=== 测试内存版本认证头构建 ===")
    
    try:
        # 创建认证上下文
        context = AuthenticationContext(
            caller_did=credentials.did_document.did,
            target_did="did:wba:example.com:test:agent",
            request_url="http://example.com/test",
            method="GET",
            use_two_way_auth=True
        )
        
        # 使用内存版本构建器
        builder = MemoryWBAAuthHeaderBuilder()
        auth_headers = builder.build_auth_header(context, credentials)
        
        logger.info(f"✅ 内存版本认证头构建成功")
        logger.info(f"  认证头键数量: {len(auth_headers)}")
        if "Authorization" in auth_headers:
            logger.info(f"  包含Authorization头")
            logger.info(f"  认证头内容: {auth_headers['Authorization'][:100]}...")
        
        return auth_headers
        
    except Exception as e:
        logger.error(f"❌ 内存版本认证头构建失败: {e}")
        return None

def test_memory_auth_wrapper(credentials):
    """测试内存认证包装器"""
    logger.info("=== 测试内存认证包装器 ===")
    
    try:
        # 创建包装器
        wrapper = create_memory_auth_header_client(credentials)
        
        # 测试双向认证
        auth_headers_two_way = wrapper.get_auth_header_two_way(
            "http://example.com/test",
            "did:wba:example.com:test:agent"
        )
        
        # 测试单向认证
        auth_headers_one_way = wrapper.get_auth_header("http://example.com/test")
        
        logger.info(f"✅ 内存认证包装器测试成功")
        logger.info(f"  双向认证头: {len(auth_headers_two_way)} 个键")
        logger.info(f"  单向认证头: {len(auth_headers_one_way)} 个键")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 内存认证包装器测试失败: {e}")
        return False

def test_memory_key_operations(user_data):
    """测试内存密钥操作"""
    logger.info("=== 测试内存密钥操作 ===")
    
    try:
        # 测试获取私钥字节
        private_key_bytes = user_data.get_private_key_bytes()
        if private_key_bytes:
            logger.info(f"✅ 私钥字节获取成功: {len(private_key_bytes)} 字节")
        else:
            logger.warning("⚠️ 私钥字节获取失败")
        
        # 测试获取公钥字节
        public_key_bytes = user_data.get_public_key_bytes()
        if public_key_bytes:
            logger.info(f"✅ 公钥字节获取成功: {len(public_key_bytes)} 字节")
        else:
            logger.warning("⚠️ 公钥字节获取失败")
        
        return private_key_bytes is not None and public_key_bytes is not None
        
    except Exception as e:
        logger.error(f"❌ 内存密钥操作测试失败: {e}")
        return False

def test_performance_comparison(user_data):
    """测试性能对比"""
    logger.info("=== 测试性能对比 ===")
    
    import time
    
    try:
        # 测试文件版本性能
        start_time = time.time()
        for i in range(10):
            credentials_file = DIDCredentials.from_paths(
                did_document_path=user_data.did_doc_path,
                private_key_path=user_data.did_private_key_file_path
            )
        file_time = time.time() - start_time
        
        # 测试内存版本性能
        start_time = time.time()
        for i in range(10):
            credentials_memory = user_data.get_memory_credentials()
        memory_time = time.time() - start_time
        
        logger.info(f"✅ 性能对比完成")
        logger.info(f"  文件版本 (10次): {file_time:.4f} 秒")
        logger.info(f"  内存版本 (10次): {memory_time:.4f} 秒")
        logger.info(f"  性能提升: {file_time/memory_time:.2f}x")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 性能对比测试失败: {e}")
        return False

async def run_all_tests():
    """运行所有测试"""
    logger.info("🚀 开始内存版本认证功能测试")
    logger.info("=" * 50)
    
    # 1. 测试内存凭证创建
    result = test_memory_credentials_creation()
    if not result:
        return False
    credentials, user_data = result
    
    # 2. 测试内存版本认证头构建
    auth_headers = test_memory_auth_header_building(credentials)
    if not auth_headers:
        return False
    
    # 3. 测试内存认证包装器
    wrapper_success = test_memory_auth_wrapper(credentials)
    if not wrapper_success:
        return False
    
    # 4. 测试内存密钥操作
    key_ops_success = test_memory_key_operations(user_data)
    if not key_ops_success:
        return False
    
    # 5. 测试性能对比
    perf_success = test_performance_comparison(user_data)
    if not perf_success:
        return False
    
    logger.info("=" * 50)
    logger.info("🎉 所有内存版本认证测试通过！")
    logger.info("✨ 重构成功：从文件操作迁移到内存操作")
    return True

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
