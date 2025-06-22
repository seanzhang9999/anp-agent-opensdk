import importlib
import glob
import os
import sys
import asyncio
import threading

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_user_data import save_interface_files, LocalUserDataManager
from anp_open_sdk.sdk_mode import SdkMode
from anp_open_sdk.service.router.router_agent import wrap_business_handler
from anp_open_sdk.utils.log_base import logger


import inspect


async def load_agent_from_module(yaml_path):
    logger.debug(f"\n🔎 Loading agent module from path: {yaml_path}")
    plugin_dir = os.path.dirname(yaml_path)
    handler_script_path = os.path.join(plugin_dir, "agent_handlers.py")
    register_script_path = os.path.join(plugin_dir, "agent_register.py")

    if not os.path.exists(handler_script_path):
        logger.debug(f"  - ⚠️  Skipping: No 'agent_handlers.py' found in {plugin_dir}")
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
        agent.api_config = cfg.get("api", [])  # 添加
        logger.info(f"  -> self register agent : {agent.name}")
        register_module.register(agent)
        return agent, None

    # 2. agent_llm: 存在 initialize_agent
    if hasattr(handlers_module, "initialize_agent"):
        logger.debug(f"  - Calling 'initialize_agent' in module: {base_module_name}.agent_handlers")
        agent = await handlers_module.initialize_agent()
        agent.api_config = cfg.get("api", [])  # 添加
        logger.info(f"  - self init agent: {agent.name}")
        return agent, handlers_module

    # 3. 普通配置型 agent_001 / agent_caculator
    agent = LocalAgent.from_did(cfg["did"])
    agent.name = cfg["name"]
    agent.api_config = cfg.get("api", [])  # 添加
    logger.debug(f"  -> Self-created agent instance: {agent.name}")
    for api in cfg.get("api", []):
        handler_func = getattr(handlers_module, api["handler"])
        # 判断handler_func参数，如果不是(request_data, request)，则用包装器
        sig = inspect.signature(handler_func)
        params = list(sig.parameters.keys())
        # 只要不是(request_data, request)，就用包装器
        if params != [ "request","request_data"]:
            handler_func = wrap_business_handler(handler_func)
        agent.expose_api(api["path"], handler_func, methods=[api["method"]])
        logger.info(f"  - config register agent: {agent.name}，api:{api}")
    return agent, None


async def main():
    logger.debug("🚀 Starting Agent Host Application...")
    if os.getcwd() not in sys.path:
        sys.path.append(os.getcwd())

    # --- 加载和初始化所有Agent模块 ---
    agent_files = glob.glob("anp_open_sdk/agents_config/*/agent_mappings.yaml")

    if not agent_files:
        logger.info("No agent configurations found. Exiting.")
        return

    preparation_tasks = [load_agent_from_module(f) for f in agent_files]
    prepared_agents_info = await asyncio.gather(*preparation_tasks)

    # 过滤掉加载失败的
    valid_agents_info = [info for info in prepared_agents_info if info and info[0]]

    all_agents = [info[0] for info in valid_agents_info]
    lifecycle_modules = {info[0].id: info[1] for info in valid_agents_info}

    if not all_agents:
        logger.info("No agents were loaded successfully. Exiting.")
        return

    # --- 启动SDK ---
    sdk = ANPSDK(mode=SdkMode.MULTI_AGENT_ROUTER, agents=all_agents)

    for agent in all_agents:
        await generate_and_save_agent_interfaces(agent, sdk)


    # 用线程启动 server
    def run_server():
        sdk.start_server()
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    logger.info("\n🔥 Server is running. Press Ctrl+C to stop.")

    logger.debug("\n🔍 Searching for an agent with discovery capabilities...")
    discovery_agent = None
    for agent in all_agents:
        if hasattr(agent, 'discover_and_describe_agents'):
            discovery_agent = agent
            break

    if discovery_agent:
        logger.info(f"✅ Found discovery agent: '{discovery_agent.name}'. Starting its discovery task...")
        # 直接调用 agent 实例上的方法
        publisher_url = "http://localhost:9527/publisher/agents"
        #result = await discovery_agent.discover_and_describe_agents(publisher_url)
        #result = await discovery_agent.run_calculator_add_demo()
        #result = await discovery_agent.run_hello_demo()
        #result = await discovery_agent.run_ai_crawler_demo()
        result = await discovery_agent.run_ai_root_crawler_demo()

    else:
        logger.debug("⚠️ No agent with discovery capabilities was found.")

    input("按任意键停止服务")

    # --- 清理 ---
    logger.debug("\n🛑 Shutdown signal received. Cleaning up...")

    # 停止服务器
    # 注意：start_server() 是在单独线程中调用的，sdk.stop_server() 只有在 ANPSDK 实现了对应的停止机制时才有效
    if 'sdk' in locals():
        logger.debug("  - Stopping server...")
        if hasattr(sdk, "stop_server"):
            sdk.stop_server()
            logger.debug("  - Server stopped.")
        else:
            logger.debug("  - sdk 实例没有 stop_server 方法，无法主动停止服务。")

    # 清理 Agent
    cleanup_tasks = []
    for agent in all_agents:
        module = lifecycle_modules.get(agent.id)
        if module and hasattr(module, "cleanup_agent"):
            logger.debug(f"  - Scheduling cleanup for module of agent: {agent.name}...")
            cleanup_tasks.append(module.cleanup_agent())

    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks)
    logger.debug("✅ All agents cleaned up. Exiting.")




def generate_custom_openapi_from_router(agent):
    openapi = {
        "openapi": "3.0.0",
        "info": {
            "title": f"{agent.name}Agent API",
            "version": "1.0.0"
        },
        "paths": {}
    }
     # 获取 summary 信息
    api_registry = None
    try:
        from anp_open_sdk.anp_sdk import ANPSDK
        api_registry = getattr(ANPSDK.instance, "api_registry", {}).get(agent.id, [])
    except Exception:
        api_registry = []

    summary_map = {item["path"].replace(f"/agent/api/{agent.id}", ""): item["summary"] for item in api_registry}


   # 遍历 agent.api_routes
    for path, handler in agent.api_routes.items():
       # 自动获取参数名（排除 request_data, request）
        sig = inspect.signature(handler)
        param_names = [p for p in sig.parameters if p not in ("request_data", "request")]

        # 构建 properties
        properties = {name: {"type": "string"} for name in param_names}

        summary = summary_map.get(path, handler.__doc__ or f"{agent.name}的{path}接口")

        openapi["paths"][path] = {
            "post": {
                "summary": summary,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": properties
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "返回结果",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object"
                                    # 这里可以根据需要补充返回内容
                                }
                            }
                        }
                    }
                }
            }
        }
    return openapi

async def generate_and_save_agent_interfaces(agent, sdk):
    """
    为指定的 agent 生成并保存 OpenAPI (YAML) 和 JSON-RPC 接口文件。
    """
    logger.debug(f"开始为 agent '{agent.name}' ({agent.id}) 生成接口文件...")

    # 1. 获取 agent 的用户数据和存储路径
    user_data_manager = LocalUserDataManager()
    user_data = user_data_manager.get_user_data(agent.id)
    if not user_data:
        logger.error(f"无法找到 agent '{agent.name}' 的用户数据，无法保存接口文件。")
        return
    user_full_path = user_data.user_dir

    # 2. 生成并保存 OpenAPI YAML 文件
    try:
        openapi_data= generate_custom_openapi_from_router(agent)
        await save_interface_files(
            user_full_path=user_full_path,
            interface_data=openapi_data,
            inteface_file_name=f"api_interface.yaml",
            interface_file_type="YAML"
        )
    except Exception as e:
        logger.error(f"为 agent '{agent.name}' 生成 OpenAPI YAML 文件失败: {e}")

    # 3. 生成并保存 JSON-RPC 文件
    try:
        jsonrpc_data = {
            "jsonrpc": "2.0",
            "info": {
                "title": f"{agent.name} JSON-RPC Interface",
                "version": "0.1.0",
                "description": f"Methods offered by {agent.name}"
            },
            "methods": []
        }

        for api in getattr(agent, "api_config", []):
            path = api["path"]
            method_name = path.strip('/').replace('/', '.')
            # 优先用yaml里的params/result
            params = api.get("params")
            result = api.get("result")
            if params is not None:
                # 保持结构化
                params_out = params
            else:
                # 兼容老逻辑
                sig = inspect.signature(agent.api_routes[path])
                params_out = {
                    name: {
                        "type": param.annotation.__name__ if (
                                param.annotation != inspect._empty and hasattr(param.annotation, "__name__")
                        ) else "Any"
                    }
                    for name, param in sig.parameters.items()
                    if name != "self"
                }
            method_obj = {
                "name": method_name,
                "summary": api.get("summary", api.get("handler", "")),
                "params": params_out
            }
            if result is not None:
                method_obj["result"] = result
            # 新增 meta 字段

            openapi_version = api.get("openapi_version", "3.0.0"),
            title = api.get("title", "ANP Agent API"),
            version = api.get("version", "1.0.0"),
            method_obj["meta"] = {
                "openapi": openapi_version,
                "info": {
                    "title": title,  # 你可以用 agent.name 或 api.title
                    "version": version
                },
                "httpMethod": api.get("method", "POST"),
                "endpoint": api.get("path")
            }
            jsonrpc_data["methods"].append(method_obj)

        await save_interface_files(
            user_full_path=user_full_path,
            interface_data=jsonrpc_data,
            inteface_file_name="api_interface.json",
            interface_file_type="JSON"
        )
    except Exception as e:
        logger.error(f"为 agent '{agent.name}' 生成 JSON-RPC 文件失败: {e}")





if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass