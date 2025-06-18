from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.sdk_mode import SdkMode
import importlib
import glob
import yaml
import os
import sys


def load_agent_ablilty(yaml_path):
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    agent = LocalAgent.from_did(cfg["did"])
    agent.name = cfg["name"]
    # 1. 优先查找自定义注册脚本
    reg_script = os.path.join(os.path.dirname(yaml_path), "agent_register.py")
    if os.path.exists(reg_script):
        rel_path = os.path.relpath(reg_script, start=os.getcwd())
        module_name = rel_path.replace(os.sep, ".").replace(".py", "")
        sys.path.append(os.getcwd())
        reg_module = importlib.import_module(module_name)
        reg_module.register(agent)
    else:
        # 2. 没有自定义注册脚本时，自动 expose_api（你的 for api in ... 逻辑）
        yaml_dir = os.path.dirname(yaml_path)
        handler_module_path = os.path.join(yaml_dir, "agent_handlers.py")
        rel_path = os.path.relpath(handler_module_path, start=os.getcwd())
        module_name = rel_path.replace(os.sep, ".").replace(".py", "")
        sys.path.append(os.getcwd())
        try:
            handler_module = importlib.import_module(module_name)
        except Exception:
            handler_module = None
        for api in cfg.get("api", []):
            handler = None
            if handler_module:
                try:
                    handler = getattr(handler_module, api["handler"])
                except Exception:
                    pass
            if not handler:
                async def handler(request_data, request):
                    return {"msg": f"default handler for {api['path']}"}
            agent.expose_api(api["path"], handler, methods=[api["method"]])
    return agent


if __name__ == "__main__":
    agent_files = glob.glob("anp_open_sdk/agents_config/agent*/agent_mappings.yaml")
    agents = [load_agent_ablilty(f) for f in agent_files]
    sdk = ANPSDK(mode=SdkMode.MULTI_AGENT_ROUTER, agents=agents)
    import threading
    def start_sdk_server():
        sdk.start_server()

    server_thread = threading.Thread(target=start_sdk_server)
    server_thread.start()