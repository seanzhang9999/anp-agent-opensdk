from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.sdk_mode import SdkMode

if __name__ == "__main__":
    agent = LocalAgent(...)
    agent.start(SdkMode.AGENT_WS_PROXY_CLIENT, ws_proxy_url="ws://127.0.0.1:9527/ws/agent", host="0.0.0.0", port=9001)