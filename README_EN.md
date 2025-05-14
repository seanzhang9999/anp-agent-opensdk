# anp agent opensdk

anp agent opensdk is dedicated to providing Agent developers with a quick-start, easy-to-integrate SDK, helping you efficiently develop, integrate, and experience ANP protocol-based agents.

## Project Goals

- Provide Agent developers with a ready-to-use SDK to lower the integration threshold.
- Help users intuitively understand the key capabilities and workflow of the SDK through an automatic demo script.
- Offer detailed integration steps to help developers quickly connect their own Agents to the ANP network.
- Support discovery, authentication, exploration, and interoperability of Agents across multiple processes or hosts.

## Automatic Demo Script

The project includes an automatic demo script. After starting, users can experience the complete SDK process, with key steps output to the console for easy understanding:

1. Start the local Agent and register it to the ANP network
2. Discover other Agents and fetch their description information
3. Perform identity authentication and trust verification
4. Initiate exploration and interoperability requests

> Start the demo script:
>
> ```bash
> python demo_autorun.py
> ```
>
> You will see detailed output and key interaction processes for each step.

## Agent Integration Steps

1. **Implement Agent core capabilities**: Develop the core logic of your Agent.
2. **Introduce anp agent opensdk**: Integrate this SDK into your project.
3. **Implement ANP protocol adaptation**: Refer to the sample code to implement ANP protocol interfaces (such as identity, discovery, authentication, exploration, interoperability, etc.).
4. **Register and publish Agent**: Use the registration interface provided by the SDK to publish your Agent to the ANP network.
5. **Test and debug**: Use the automatic demo script or manually call interfaces to verify the integration effect.

For detailed integration documentation, please refer to [doc/architecture](doc/architecture/) and sample code.

## Runtime Experience

Supports interoperability experience of Agents across multiple processes or hosts:

- Each Agent can run independently on different processes or hosts and automatically discover each other via the ANP protocol.
- Supports identity authentication and trust verification to ensure secure communication.
- Can initiate exploration and interoperability requests to experience cross-Agent collaboration.

> You can run demo_autorun.py on multiple hosts to experience Agent discovery and interoperability in a real network environment.

## Directory Structure

```
.
├── anp_core/            # ANP protocol core interfaces
├── anp_mcpwrapper/      # MCP protocol adaptation
├── api/                 # API routing module
├── core/                # Application framework
├── doc/                 # Documentation and samples
├── examples/            # Integration examples
├── utils/               # Utility functions
├── logs/                # Logs
├── demo_autorun.py      # Automatic demo script
├── ...
```

## Quick Start

1. Clone the project and install dependencies
2. Configure the .env file
3. Run demo_autorun.py to experience the automatic demo
4. Integrate the SDK into your Agent project following the integration steps

## Reference Documentation

- [ANP Protocol Specification](https://github.com/agent-network-protocol/AgentNetworkProtocol)
- [doc/architecture](doc/architecture/)
- Sample code and automatic demo script

Feedback and contributions are welcome to help improve anp agent opensdk!
