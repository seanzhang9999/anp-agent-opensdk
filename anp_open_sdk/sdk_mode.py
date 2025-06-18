from enum import Enum

class SdkMode(Enum):
    AGENT_SELF_SERVICE = "agent_self_service"          # 1
    MULTI_AGENT_ROUTER = "multi_agent_router"          # 2
    DID_REG_PUB_SERVER = "did_reg_pub_server"          # 3
    AGENT_WS_PROXY_CLIENT = "agent_ws_proxy_client"    # 4
    SDK_WS_PROXY_SERVER = "sdk_ws_proxy_server"        # 5