import os
import importlib
import inspect
import yaml
import logging
from typing import Dict, List, Optional, Tuple, Any

from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager, save_interface_files
from anp_open_sdk.service.router.router_agent import wrap_business_handler

logger = logging.getLogger(__name__)

class LocalAgentManager:
    """本地 Agent 管理器，负责加载、注册和生成接口文档"""

    @staticmethod
    def load_agent_from_module(yaml_path: str) -> Tuple[Optional[LocalAgent], Optional[Any]]:
        """从模块路径加载 Agent 实例"""
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

        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # 1. agent_002: 存在 agent_register.py，优先自定义注册
        if os.path.exists(register_script_path):
            register_module = importlib.import_module(f"{base_module_name}.agent_register")
            agent = LocalAgent.from_did(cfg["did"])
            agent.name = cfg["name"]
            agent.api_config = cfg.get("api", [])
            logger.info(f"  -> self register agent : {agent.name}")
            register_module.register(agent)
            return agent, None

        # 2. agent_llm: 存在 initialize_agent
        if hasattr(handlers_module, "initialize_agent"):
            logger.debug(f"  - Calling 'initialize_agent' in module: {base_module_name}.agent_handlers")
            agent = LocalAgent.from_did(cfg["did"])
            agent.name = cfg["name"]
            agent.api_config = cfg.get("api", [])
            logger.info(f"  - pre-init agent: {agent.name}")
            return agent, handlers_module

        # 3. 普通配置型 agent_001 / agent_caculator
        agent = LocalAgent.from_did(cfg["did"])
        agent.name = cfg["name"]
        agent.api_config = cfg.get("api", [])
        logger.debug(f"  -> Self-created agent instance: {agent.name}")
        for api in cfg.get("api", []):
            handler_func = getattr(handlers_module, api["handler"])
            sig = inspect.signature(handler_func)
            params = list(sig.parameters.keys())
            if params != ["request", "request_data"]:
                handler_func = wrap_business_handler(handler_func)
            agent.expose_api(api["path"], handler_func, methods=[api["method"]])
            logger.info(f"  - config register agent: {agent.name}，api:{api}")
        return agent, None

    @staticmethod
    def generate_custom_openapi_from_router(agent: LocalAgent,sdk) -> Dict:
        """根据 Agent 的路由生成自定义的 OpenAPI 规范"""
        openapi = {
            "openapi": "3.0.0",
            "info": {
                "title": f"{agent.name}Agent API",
                "version": "1.0.0"
            },
            "paths": {}
        }
        api_registry = getattr(sdk, "api_registry", {}).get(agent.id, [])
        summary_map = {item["path"].replace(f"/agent/api/{agent.id}", ""): item["summary"] for item in api_registry}

        for path, handler in agent.api_routes.items():
            sig = inspect.signature(handler)
            param_names = [p for p in sig.parameters if p not in ("request_data", "request")]
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
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            }
        return openapi

    @staticmethod
    async def generate_and_save_agent_interfaces(agent: LocalAgent,sdk):
        """为指定的 agent 生成并保存 OpenAPI (YAML) 和 JSON-RPC 接口文件"""
        logger.debug(f"开始为 agent '{agent.name}' ({agent.id}) 生成接口文件...")
        user_data_manager = LocalUserDataManager()
        user_data = user_data_manager.get_user_data(agent.id)
        if not user_data:
            logger.error(f"无法找到 agent '{agent.name}' 的用户数据，无法保存接口文件。")
            return
        user_full_path = user_data.user_dir

        # 2. 生成并保存 OpenAPI YAML 文件
        try:
            openapi_data = LocalAgentManager.generate_custom_openapi_from_router(agent,sdk)
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
                params = api.get("params")
                result = api.get("result")
                if params is None:
                    sig = inspect.signature(agent.api_routes[path])
                    params = {
                        name: {"type": param.annotation.__name__ if (param.annotation != inspect._empty and hasattr(param.annotation, "__name__")) else "Any"}
                        for name, param in sig.parameters.items() if name != "self"
                    }
                method_obj = {"name": method_name, "summary": api.get("summary", api.get("handler", "")), "params": params}
                if result is not None:
                    method_obj["result"] = result

                method_obj["meta"] = {
                    "openapi": api.get("openapi_version", "3.0.0"),
                    "info": {"title": api.get("title", "ANP Agent API"), "version": api.get("version", "1.0.0")},
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
