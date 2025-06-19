import importlib
import glob
import os
import sys
import asyncio
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.sdk_mode import SdkMode


async def load_agent_from_module(yaml_path):
    """
    新的加载逻辑：
    1. 动态导入插件模块。
    2. 调用模块的 `initialize_agent` 函数。
    3. 收集返回的 agent 实例。
    """
    print(f"\n🔎 Loading agent module from path: {yaml_path}")

    # 根据YAML路径找到对应的handlers.py或register.py
    plugin_dir = os.path.dirname(yaml_path)
    # 假设所有逻辑都在 agent_handlers.py 中
    handler_script_path = os.path.join(plugin_dir, "agent_handlers.py")

    if not os.path.exists(handler_script_path):
        print(f"  - ⚠️  Skipping: No 'agent_handlers.py' found in {plugin_dir}")
        return None, None

    # 将 'anp_open_sdk/agents_config/llm_agent' 转换为 'anp_open_sdk.agents_config.llm_agent'
    module_path_prefix = os.path.dirname(plugin_dir).replace(os.sep, ".")
    module_name = f"{module_path_prefix}.{os.path.basename(plugin_dir)}.agent_handlers"

    try:
        # 动态导入插件模块
        plugin_module = importlib.import_module(module_name)

        # 检查并调用初始化钩子
        if hasattr(plugin_module, "initialize_agent"):
            print(f"  - Calling 'initialize_agent' in module: {module_name}")
            # 调用函数并获取它自己创建的agent实例
            agent_instance = await plugin_module.initialize_agent()
            print(f"  - Module returned agent: {agent_instance.name}")
            return agent_instance, plugin_module
        else:
            print(f"  - ⚠️  Skipping: 'initialize_agent' function not found in {module_name}")
            return None, None

    except Exception as e:
        print(f"  - ❌ Error loading module {module_name}: {e}")
        return None, None


async def main():
    print("🚀 Starting Agent Host Application...")
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())

    # --- 加载和初始化所有Agent模块 ---
    agent_files = glob.glob("anp_open_sdk/agents_config/*/agent_mappings.yaml")

    if not agent_files:
        print("No agent configurations found. Exiting.")
        return

    preparation_tasks = [load_agent_from_module(f) for f in agent_files]
    prepared_agents_info = await asyncio.gather(*preparation_tasks)

    # 过滤掉加载失败的
    valid_agents_info = [info for info in prepared_agents_info if info and info[0]]

    all_agents = [info[0] for info in valid_agents_info]
    lifecycle_modules = {info[0].did: info[1] for info in valid_agents_info}

    if not all_agents:
        print("No agents were loaded successfully. Exiting.")
        return

    # --- 启动SDK ---
    sdk = ANPSDK(mode=SdkMode.MULTI_AGENT_ROUTER, agents=all_agents)

    # ... (注入SDK到总控的逻辑可以保持，但总控自己也需要遵循这个新模式)

    server_task = sdk.start_server()

    print("\n🔥 Server is running. Press Ctrl+C to stop.")
    try:
        await server_task
    finally:
        # --- 清理 ---
        print("\n🛑 Shutdown signal received. Cleaning up agents...")
        cleanup_tasks = []
        for agent in all_agents:
            module = lifecycle_modules.get(agent.did)
            if module and hasattr(module, "cleanup_agent"):
                print(f"  - Scheduling cleanup for module of agent: {agent.name}...")
                cleanup_tasks.append(module.cleanup_agent())  # cleanup也不再需要agent参数

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)
        print("✅ All agents cleaned up. Exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass