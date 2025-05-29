#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

print("Python版本:", sys.version)
print("当前工作目录:", os.getcwd())
print("Python路径:", sys.path[:3])  # 只显示前3个路径

try:
    print("尝试导入 anp_open_sdk...")
    from anp_open_sdk.anp_sdk import ANPSDK
    print("✓ anp_open_sdk 导入成功")
except ImportError as e:
    print("✗ anp_open_sdk 导入失败:", e)
    sys.exit(1)

try:
    print("尝试导入 demo_modules...")
    from demo_modules.step_helper import DemoStepHelper
    print("✓ demo_modules 导入成功")
except ImportError as e:
    print("✗ demo_modules 导入失败:", e)
    print("请检查是否在正确的目录下运行")
    sys.exit(1)

try:
    print("尝试导入其他模块...")
    from demo_modules.agent_loader import DemoAgentLoader
    from services.sdk_manager import DemoSDKManager
    print("✓ 所有模块导入成功")
except ImportError as e:
    print("✗ 模块导入失败:", e)
    sys.exit(1)

print("尝试创建基础组件...")
try:
    step_helper = DemoStepHelper(step_mode=False)
    print("✓ DemoStepHelper 创建成功")
    
    sdk_manager = DemoSDKManager()
    print("✓ DemoSDKManager 创建成功")
    
    print("尝试初始化SDK...")
    sdk = sdk_manager.initialize_sdk()
    print("✓ SDK 初始化成功")
    
except Exception as e:
    print("✗ 组件创建失败:", e)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n🎉 所有基础测试通过！")
print("现在可以尝试运行完整的演示程序")