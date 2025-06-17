from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.sdk_mode import SdkMode

if __name__ == "__main__":
    agent = LocalAgent(...)  # 填写必要参数
    agent.start(SdkMode.AGENT_SELF_SERVICE, host="0.0.0.0", port=9000)