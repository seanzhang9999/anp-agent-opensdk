# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import yaml
import json
import os
import sys

# Add the project root to the sys.path to allow importing anp_open_sdk
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver

# Simulate the setup from anp_sdk_demo.py
# We need a dummy user directory and DID document for LocalAgent initialization
# In a real scenario, you would use existing user data.

async def generate_openapi_yaml():
    # Create a dummy user directory and DID document for demonstration
    # This is a simplified version for generating the schema without full user setup
    dummy_user_dir_name = "dummy_agent_for_openapi"
    dummy_user_dir_path = os.path.join(path_resolver.resolve_path(dynamic_config.get('anp_sdk.user_did_path')), dummy_user_dir_name)
    os.makedirs(dummy_user_dir_path, exist_ok=True)
    dummy_did_doc_path = os.path.join(dummy_user_dir_path, 'did_document.json')
    dummy_private_key_path = os.path.join(dummy_user_dir_path, 'private_key.pem')

    # Create dummy DID document and private key files if they don't exist
    if not os.path.exists(dummy_did_doc_path):
        dummy_did_doc_content = {
            "@context": "https://www.w3.org/ns/did/v1",
            "id": f"did:example:{dummy_user_dir_name}",
            "verificationMethod": [
                {
                    "id": f"did:example:{dummy_user_dir_name}#key1",
                    "type": "JsonWebKey2020",
                    "controller": f"did:example:{dummy_user_dir_name}",
                    "publicKeyJwk": {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": "dummy_public_key"
                    }
                }
            ]
        }
        with open(dummy_did_doc_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_did_doc_content, f, ensure_ascii=False, indent=2)

    if not os.path.exists(dummy_private_key_path):
         # Create a dummy private key file (content doesn't matter for schema generation)
        with open(dummy_private_key_path, 'w') as f:
            f.write("dummy_private_key_content")

    # Initialize SDK and a dummy agent
    sdk = ANPSDK()
    # Use the dummy DID from the created document
    with open(dummy_did_doc_path, 'r', encoding='utf-8') as f:
        dummy_did = json.load(f)['id']

    dummy_agent = LocalAgent(id=dummy_did, user_dir=dummy_user_dir_name)
    sdk.register_agent(dummy_agent)

    # Register the APIs similar to anp_sdk_demo.py
    @dummy_agent.expose_api("/hello")
    def hello_api(request):
        # This function body is not executed, only its existence and path matter for schema
        pass

    def info_api(request):
        # This function body is not executed
        pass
    dummy_agent.expose_api("/info", info_api)

    # Generate OpenAPI schema from the FastAPI app instance
    openapi_schema = sdk.app.openapi()

    # Filter the schema to include only the desired paths
    filtered_paths = {}
    target_paths = [
        f"/agent/api/{{agent_id}}/hello",
        f"/agent/api/{{agent_id}}/info"
    ]

    # FastAPI's openapi() generates paths relative to the app's root.
    # The actual paths exposed by the SDK's router might be different.
    # Let's inspect the generated schema to find the correct paths.
    # Based on agent_api_call.py, the paths are likely prefixed with /agent/api/{target_agent_path}
    # where {target_agent_path} is the quoted DID.
    # The generated schema will likely use a placeholder like {agent_id} or the actual dummy DID.
    # We need to find the paths that correspond to /hello and /info under the agent API prefix.

    # A more robust way is to iterate through generated paths and check if they end with /hello or /info
    agent_api_prefix_pattern = r"^/agent/api/[^/]+/"

    for path, path_item in openapi_schema.get('paths', {}).items():
        # Check if the path matches the pattern and ends with /hello or /info
        if path.endswith('/hello') or path.endswith('/info'):
             # Replace the specific dummy DID in the path with {agent_id} for a generic schema
            generic_path = path.replace(dummy_did, '{agent_id}')
            filtered_paths[generic_path] = path_item

    # Create a new schema dictionary with filtered paths and other necessary info
    filtered_schema = {
        "openapi": openapi_schema.get("openapi"),
        "info": openapi_schema.get("info"),
        "paths": filtered_paths,
        "components": openapi_schema.get("components"), # Include components if needed for schemas
        "tags": openapi_schema.get("tags") # Include tags if needed
    }

    # Convert the filtered schema to YAML
    yaml_output = yaml.dump(filtered_schema, allow_unicode=True, sort_keys=False)

    print(yaml_output)

# Run the async function
if __name__ == "__main__":
    asyncio.run(generate_openapi_yaml())