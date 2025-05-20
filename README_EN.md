# anp agent opensdk

anp agent opensdk is dedicated to providing Agent developers with a quick start and easy-to-integrate SDK, helping your own intelligent agents quickly integrate ANP protocol-based interoperability capabilities and expand the service scope for developers.

## Project Goals

- Provide Agent developers with a ready-to-use SDK to lower the integration threshold.
- Help users intuitively understand the key capabilities and workflow of the SDK through an automatic demo script.
- Offer detailed integration steps to help developers quickly connect their own Agents to the ANP network.
- Provide out-of-the-box basic interoperability capabilities for intelligent agents:
    1. Create a DID identity, bind the identity to a domain name, and publish the DID document and description to a public domain name as a basic trust source.
    2. Can perform peer-to-peer identity authentication and mutual trust verification with other Agents.
    3. Can perform peer-to-peer POST messages/receive messages from others, publish and call APIs with other Agents.
    4. In cases where peer-to-peer contact is not possible (eAs in an intranet), Agents can establish a "message group" with other Agents on a mutually confirmed SSE public service.
    5. The SSE public service can receive POSTs and push them to the target Agent via SSE, thereby completing basic message transmission between Agents.

## Automatic Demo Script

The project includes an automatic demo script designed to help users quickly understand the core functions and workflow of the SDK. After starting the script, you can automatically experience the complete process of the SDK, with key steps output to the console for easy understanding.

The demo script currently covers the following features:
1. Automatically create a DID identity through a tool and generate corresponding configuration in the user directory.
2. Load the DID identity in the Agent code.
3. Start the local ANPSDK service, which is responsible for helping the Agent publish DID-doc, APIs, and message receiving ports.
4. The same ANPSDK service can host multiple Agents and automatically route corresponding messages/API requests.
5. Agents that have started the ANPSDK service can communicate with each other through APIs (GET/POST), messages (POST), and message groups (POST+SSE).
6. For developers, they can publish external APIs on the ANPSDK service through decorators or registration methods, register message listening/message group listening handlers, or send messages to any DID user at any time.

Future demo script will cover the following features:
1. Publish Agent information to the ANP directory service.
2. Discover other Agents and retrieve their description information.
3. Initiate exploration and interoperability requests.
4. Interact with other intelligent agents through ANP's SSE public service in intranet and mobile scenarios.
5. Demonstrate a simplified version of ANPSDK, which does not require starting an HTTP server when hosting DID-doc, and only listens externally through public SSE.

> Start the demo script:
>
> ```bash
> python anp_sdk_demo.py -h

    usage: anp_sdk_demo.py [-h] [-p] [-f] [-n name host port host_dir agent_type]

    ANP SDK Demo Program

    options:
    -h, --help            show this help message and exit
    -p                    Enable step mode, each step will pause and wait for user confirmation - suitable for learning and debugging
    -f                    Fast mode, skip all steps that require user confirmation - suitable for regression testing
    -n name host port host_dir agent_type
                            Create a new user, requires: username hostname port host_directory user_type
> ```
> python anp_sdk_demo.py -n cool_anper localhost 9527 wba user
> Create a user named cool_anper, with hostname localhost, port 9527, host directory wba, and user type user.
> Its address is did:wba:localhost%3A9527%3A:wba:user:8-digit random number
> python anp_sdk_demo.py -n cool_anp_agent localhost 9527 wba agent
> Create a user named cool_anp_agent, with hostname localhost, port 9527, host directory wba, and user type agent.
> Its address is did:wba:localhost%3A9527%3A:wba:agent:unique_id (8-digit random number)
> DID and other information are stored in the /anp_open_sdk/anp_users/user_unique_id/ directory.
> The agent type will additionally create an /anp_open_sdk/anp_users/user_unique_id/agent directory for developers to configure various aspects of the agent.
> Duplicate usernames will be created as username+date+daily sequence number.



## Agent Integration Steps

1. **Based on Agent Core Capabilities**: Introduce the SDK into your intelligent agent project.
2. **Configure anp agent opensdk**: Create a DID identity and simply configure the SDK.
3. **Implement ANP Service Registration**: Refer to the example code to register your code with the ANP SDK interfaces (such as identity, discovery, authentication, exploration, interoperability, etc.).
4. **Register and Publish Agent**: Publish your Agent to the ANP network through the registration interface provided by the SDK.
5. **Test and Debug**: Use the automatic demo script or manually call interfaces to verify the integration effect.

For detailed integration documentation, please refer to [doc/architecture](doc/architecture/) and example code.

## Running Process Experience

Supports ANPSDK interoperability experience across multiple processes or hosts:

- Each ANPSDK can run independently on different processes or hosts, exchanging agent information with each other through the ANP protocol.
- Supports identity authentication and mutual trust verification to ensure communication security.
- Can initiate exploration and interoperability requests to experience Agent open interoperability and collaboration.

> You can run anp_sdk_demo.py on multiple hosts separately to experience Agent discovery and interoperability in a real network environment.



## Quick Start

1. Clone the project and install dependencies.
2. Configure the .env file.
3. Run anp_sdk_demo.py to experience the automatic demo.
4. Integrate the SDK into your Agent project according to the integration steps.

## Reference Documentation

- [ANP Protocol Specification](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- Example code and automatic demo script

Welcome feedback and suggestions to jointly improve anp agent opensdk!
This project is distributed under the Apache License 2.0. Please refer to the LICENSE file for more details