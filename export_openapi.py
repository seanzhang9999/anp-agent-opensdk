import json
import yaml
import os
import sys

# Add project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.config.dynamic_config import dynamic_config

# Initialize SDK (FastAPI app is created and default routes are registered here)
# Use the port from dynamic_config.yaml user_did_port_1
sdk = ANPSDK(port=dynamic_config.get('anp_sdk.user_did_port_1'))

# Access the FastAPI app
app = sdk.app

# Get the OpenAPI schema
# Need to call app.openapi() after routes are registered.
# The default routes are registered in ANPSDK.__init__
openapi_schema = app.openapi()

# Convert to YAML
openapi_yaml = yaml.dump(openapi_schema, allow_unicode=True, sort_keys=False)

# Define output file path
output_file = 'openapi.yaml'
output_path = os.path.join(project_root, output_file)

# Write to file
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(openapi_yaml)

print(f"OpenAPI specification exported to {output_path}")