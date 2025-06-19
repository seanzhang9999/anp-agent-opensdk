import importlib
import glob
import os
import sys
import asyncio
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.sdk_mode import SdkMode


async def load_agent_from_module(yaml_path):
    print(f"\n🔎 Loading agent module from path: {yaml_path}")
    plugin_dir = os.path.dirname(yaml_path)
    handler_script_path = os.path.join(plugin_dir, "agent_handlers.py")
    register_script_path = os.path.join(plugin_dir, "agent_register.py")

    if not os.path.exists(handler_script_path):
        print(f"  - ⚠️  Skipping: No 'agent_handlers.py' found in {plugin_dir}")
        return None, None

    module_path_prefix = os.path.dirname(plugin_dir).replace(os.sep, ".")
    base_module_name = f"{module_path_prefix}.{os.path.basename(plugin_dir)}"
    base_module_name = base_module_name.replace("/", ".")
    handlers_module = importlib.import_module(f"{base_module_name}.agent_handlers")

    import yaml
    from anp_open_sdk.anp_sdk_agent import LocalAgent

    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 1. agent_002: 存在 agent_register.py，优先自定义注册
    if os.path.exists(register_script_path):
        register_module = importlib.import_module(f"{base_module_name}.agent_register")
        agent = LocalAgent.from_did(cfg["did"])
        agent.name = cfg["name"]
        print(f"  -> Self-created agent instance: {agent.name}")
        register_module.register(agent)
        return agent, None

    # 2. agent_llm: 存在 initialize_agent
    if hasattr(handlers_module, "initialize_agent"):
        print(f"  - Calling 'initialize_agent' in module: {base_module_name}.agent_handlers")
        agent_instance = await handlers_module.initialize_agent()
        print(f"  - Module returned agent: {agent_instance.name}")
        return agent_instance, handlers_module

    # 3. 普通配置型 agent_001 / agent_caculator
    agent = LocalAgent.from_did(cfg["did"])
    agent.name = cfg["name"]
    print(f"  -> Self-created agent instance: {agent.name}")
    for api in cfg.get("api", []):
        handler_func = getattr(handlers_module, api["handler"])
        agent.expose_api(api["path"], handler_func, methods=[api["method"]])
    return agent, None


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
    lifecycle_modules = {info[0].id: info[1] for info in valid_agents_info}

    if not all_agents:
        print("No agents were loaded successfully. Exiting.")
        return

    # --- 启动SDK ---
    sdk = ANPSDK(mode=SdkMode.MULTI_AGENT_ROUTER, agents=all_agents)

    # 不使用await，因为start_server返回的是Thread对象
    server_thread = sdk.start_server()


    print("\n🔥 Server is running. Press Ctrl+C to stop.")
    try:
        # 保持主协程运行，直到收到中断信号
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        # --- 清理 ---
        print("\n🛑 Shutdown signal received. Cleaning up agents...")
        cleanup_tasks = []
        for agent in all_agents:
            module = lifecycle_modules.get(agent.id)
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