#!/usr/bin/env python3
"""
ANP SDK Demo 自动化集成测试

本脚本自动化测试 anp_open_sdk_demo 的主要演示功能，确保各主要流程可正常跑通。
"""

import sys
import asyncio
import traceback
from pathlib import Path

import logging
from anp_open_sdk.utils.log_base import setup_logging
from anp_open_sdk.config import UnifiedConfig,set_global_config

app_config = UnifiedConfig(config_file='anp_open_sdk_framework_demo_agent_unified_config.yaml')
set_global_config(app_config)

setup_logging() # 假设 setup_logging 内部也改用 get_global_config()
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from anp_open_sdk_demo.demo_modules.step_helper import DemoStepHelper
from anp_open_sdk_demo.demo_modules.agent_loader import DemoAgentLoader
from anp_open_sdk_demo.demo_modules.agent_batch_registry import DemoAgentRegistry
from anp_open_sdk_demo.demo_modules.demo_tasks import DemoTaskRunner
from anp_open_sdk_demo.services.dns_service import DemoDNSService
from anp_open_sdk_demo.services.sdk_manager import DemoSDKManager

def setup_demo_env():
    """初始化演示环境，返回 DemoTaskRunner 和 agent 列表"""
    step_helper = DemoStepHelper(step_mode=False)
    dns_service = DemoDNSService(base_domain='localhost')
    sdk_manager = DemoSDKManager()
    agent_loader = DemoAgentLoader()
    agent_registry = DemoAgentRegistry()
    sdk = sdk_manager.initialize_sdk()
    agents = agent_loader.load_demo_agents(sdk)


    agent_registry.register_api_handlers(agents)
    agent_registry.register_message_handlers(agents)
    agent_registry.register_group_event_handlers(agents)


    for agent in agents:
        sdk.register_agent(agent)

    task_runner = DemoTaskRunner(sdk, agents, step_helper)
    sdk_manager.start_server(sdk)
    return task_runner, agents

async def test_anp_tool_crawler(task_runner, agents):
    logger.info("\n=== 测试1: 智能体信息爬虫演示 ===")
    try:
        await task_runner.run_anp_tool_crawler_agent_search_ai_ad_jason(agents[0], agents[1])
        logger.info("✅ 智能体信息爬虫演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ 智能体信息爬虫演示失败: {e}")
        traceback.print_exc()
        return False

async def test_api_demo(task_runner, agents):
    logger.info("\n=== 测试2: API 调用演示 ===")
    try:
        await task_runner.run_api_demo(agents[0], agents[1])
        logger.info("✅ API 调用演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ API 调用演示失败: {e}")
        traceback.print_exc()
        return False

async def test_message_demo(task_runner, agents):
    logger.info("\n=== 测试3: 消息发送演示 ===")
    try:
        await task_runner.run_message_demo(agents[1], agents[2], agents[0])
        logger.info("✅ 消息发送演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ 消息发送演示失败: {e}")
        traceback.print_exc()
        return False

async def test_agent_lifecycle(task_runner, agents):
    logger.info("\n=== 测试4: 智能体生命周期演示 ===")
    try:
        await task_runner.run_agent_lifecycle_demo(agents[0], agents[1], agents[2])
        logger.info("✅ 智能体生命周期演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ 智能体生命周期演示失败: {e}")
        traceback.print_exc()
        return False

async def test_hosted_did(task_runner, agents):
    logger.info("\n=== 测试5: 托管 DID 演示 ===")
    try:
        await task_runner.run_hosted_did_demo(agents[0])
        logger.info("✅ 托管 DID 演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ 托管 DID 演示失败: {e}")
        traceback.print_exc()
        return False

async def test_group_chat(task_runner, agents):
    logger.info("\n=== 测试6: 群聊演示 ===")
    try:
        await task_runner.run_group_chat_demo(agents[0], agents[1], agents[2])
        logger.info("✅ 群聊演示通过")
        return True
    except Exception as e:
        logger.error(f"❌ 群聊演示失败: {e}")
        traceback.print_exc()
        return False

async def run_all_tests():
    logger.info("🚀 开始 ANP SDK 全部演示自动化测试")
    logger.info("=" * 50)
    task_runner, agents = setup_demo_env()
    if len(agents) < 3:
        logger.error("智能体不足3个，无法执行全部演示")
        return False

    tests = [
        test_anp_tool_crawler,
        test_api_demo,
        test_message_demo,
        test_agent_lifecycle,
        test_hosted_did,
        test_group_chat,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = await test(task_runner, agents)
            if result:
                passed += 1
                logger.info("✅ 通过")
            else:
                failed += 1
                logger.error("❌ 失败")
        except Exception as e:
            failed += 1
            logger.error(f"❌ 异常: {e}")

    logger.info("\n" + "=" * 50)
    logger.info(f"📊 测试结果: {passed} 通过, {failed} 失败")

    if failed == 0:
        logger.info("🎉 所有演示通过！ANP SDK 工作正常。")
    else:
        logger.warning("⚠️  部分演示失败，请检查环境和配置。")

    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)