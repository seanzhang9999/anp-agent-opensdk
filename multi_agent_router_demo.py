from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.sdk_mode import SdkMode

if __name__ == "__main__":
    agent1 = LocalAgent(...)
    agent2 = LocalAgent(...)
    sdk = ANPSDK(mode=SdkMode.MULTI_AGENT_ROUTER, agents=[agent1, agent2])
    sdk.start_server()