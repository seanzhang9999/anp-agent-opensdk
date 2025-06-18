from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.sdk_mode import SdkMode

if __name__ == "__main__":
    agent1 = LocalAgent(...)
    agent2 = LocalAgent(...)
    sdk = ANPSDK(mode=SdkMode.SDK_WS_PROXY_SERVER, agents=[agent1, agent2], ws_host="0.0.0.0", ws_port=9527)
    sdk.start_server()