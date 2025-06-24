#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2024 ANP Open SDK Authors

"""ANP SDK 综合演示程序"""
import sys
import argparse
import asyncio
import traceback
import logging
from anp_open_sdk.utils.log_base import setup_logging
from anp_open_sdk.config import UnifiedConfig,set_global_config

app_config = UnifiedConfig(config_file='anp_open_sdk_framework_demo_agent_unified_config.yaml')
set_global_config(app_config)

setup_logging() # 假设 setup_logging 内部也改用 get_global_config()
logger = logging.getLogger(__name__)


logger.debug("启动 ANP Demo...")
logger.debug(f"Python版本: {sys.version}")
logger.debug(f"工作目录: {sys.path[0]}")
try:
    logger.debug("导入模块...")
    from anp_open_sdk_demo.demo_modules.step_helper import DemoStepHelper
    from anp_open_sdk_demo.demo_modules.agent_loader import DemoAgentLoader
    from anp_open_sdk_demo.demo_modules.agent_batch_registry import DemoAgentRegistry
    from anp_open_sdk_demo.demo_modules.demo_tasks import DemoTaskRunner
    from anp_open_sdk_demo.services.dns_service import DemoDNSService
    from anp_open_sdk_demo.services.sdk_manager import DemoSDKManager

    logger.debug("✓ 所有模块导入成功")
except ImportError as e:
    logger.debug(f"✗ 模块导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)
        
    
class ANPDemoApplication:
    """ANP SDK 演示应用程序主类"""

    def __init__(self, args):
        logger.debug("初始化 ANPDemoApplication...")
        self.args = args

        try:
            self.step_helper = DemoStepHelper(step_mode=args.s)


            # 初始化服务
            self.dns_service = DemoDNSService(base_domain=getattr(args, 'domain', 'localhost'))
            self.sdk_manager = DemoSDKManager()

            # 初始化组件
            self.agent_loader = DemoAgentLoader()
            self.agent_registry = DemoAgentRegistry()

            # 运行时状态
            self.agents = []
            self.sdk = None

            logger.debug("✓ ANPDemoApplication 初始化成功")
        except Exception as e:
            logger.debug(f"✗ ANPDemoApplication 初始化失败: {e}")
            traceback.print_exc()
            raise

    def run(self):
        """主运行方法"""
        try:
            logger.debug("开始运行演示...")
            self.step_helper.pause("ANP SDK 演示程序启动")

            # 初始化SDK和agents
            self._initialize_components()

            # 选择运行模式
            if self.args.d:
                self._run_development_mode()
            elif self.args.s:
                self._run_step_mode()
            elif self.args.f:
                self._run_fast_mode()
            else:
            # 默认开发模式
                self._run_development_mode()

        except KeyboardInterrupt:
            logger.debug("用户中断演示")
        except Exception as e:
            logger.error(f"Demo运行错误: {e}")
            traceback.print_exc()
        finally:
            self._cleanup()

    def _initialize_components(self):
        """初始化所有组件"""
        try:
            logger.debug("初始化组件...")
            self.step_helper.pause("初始化SDK")

            # 初始化SDK
            self.sdk = self.sdk_manager.initialize_sdk()

            # 加载agents
            self.step_helper.pause("加载智能体")
            self.agents = self.agent_loader.load_demo_agents(self.sdk)

            if len(self.agents) < 3:
                logger.error("智能体不足3个，无法完成全部演示")
                logger.debug(f"当前找到 {len(self.agents)} 个智能体")
                for i, agent in enumerate(self.agents):
                    logger.debug(f"  {i+1}. {agent.name} ({agent.id})")
                return

            # 注册API和消息处理器
            self.step_helper.pause("注册处理器")
            self.agent_registry.register_api_handlers(self.agents)
            self.agent_registry.register_message_handlers(self.agents)
            self.agent_registry.register_group_event_handlers(self.agents)

            # 注册agents到SDK
            self.step_helper.pause("注册智能体到SDK")
            for agent in self.agents:
                self.sdk.register_agent(agent)

            # 启动服务器
            self.step_helper.pause("启动服务器")
            self.sdk_manager.start_server(self.sdk)

            if not self.args.f:  # 快速模式不显示提示
                logger.debug("服务器已启动，查看'/'了解状态,'/docs'了解基础api")

            logger.debug("✓ 组件初始化完成")

        except Exception as e:
            logger.error(f"组件初始化失败: {e}")
            traceback.print_exc()
            raise

    def _run_development_mode(self):
        """开发模式"""
        logger.debug("启动开发模式演示")

        task_runner = DemoTaskRunner(
            sdk=self.sdk,
            agents=self.agents,
            step_helper=self.step_helper,
            dev_mode=True
        )

        asyncio.run(task_runner.run_all_demos())

    def _run_step_mode(self):
        """分步执行模式"""
        logger.debug("启动分步执行模式演示")

        task_runner = DemoTaskRunner(
            sdk=self.sdk,
            agents=self.agents,
            step_helper=self.step_helper,
            step_mode=True
        )

        asyncio.run(task_runner.run_all_demos())

    def _run_fast_mode(self):
        """快速执行模式"""
        logger.debug("启动快速执行模式演示")

        task_runner = DemoTaskRunner(
            sdk=self.sdk,
            agents=self.agents,
            step_helper=self.step_helper,
            fast_mode=True
        )

        asyncio.run(task_runner.run_all_demos())

    def _cleanup(self):
        """清理资源"""
        logger.debug("开始清理资源...")
        try:
            if self.sdk:
                self.sdk_manager.stop_server(self.sdk)
            if self.dns_service:
                self.dns_service.stop()
            logger.debug("资源清理完成")
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")


def main():
    try:
        logger.debug("解析命令行参数...")
        parser = argparse.ArgumentParser(description='ANP SDK 综合演示程序')
        parser.add_argument('-d', action='store_true', help='开发测试模式')
        parser.add_argument('-s', action='store_true', help='步骤执行模式')
        parser.add_argument('-f', action='store_true', help='快速执行模式')
        parser.add_argument('--domain', default='localhost', help='指定测试域名')

        args = parser.parse_args()

        # 默认开发模式
        if not (args.d or args.s or args.f):
            args.d = True
    
        logger.debug(f"运行模式: {'开发模式' if args.d else '步骤模式' if args.s else '快速模式'}")

        demo_app = ANPDemoApplication(args)
        demo_app.run()

    except Exception as e:
        logger.debug(f"程序执行失败: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()