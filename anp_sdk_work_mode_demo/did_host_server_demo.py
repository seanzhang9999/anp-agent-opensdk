from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.sdk_mode import SdkMode

if __name__ == "__main__":
    sdk = ANPSDK(mode=SdkMode.DID_HOST_SERVER)
    sdk.start_server()