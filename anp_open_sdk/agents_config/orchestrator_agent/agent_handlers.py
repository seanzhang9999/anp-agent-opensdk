import asyncio

# 这个全局变量将由主应用在启动时注入，赋予总控调用其他agent的能力
sdk_instance = None

def set_sdk_for_orchestration(sdk):
    """
    这是一个特殊的注入函数，由主应用调用。
    它让本模块获得了调用系统中任何其他Agent的能力。
    """
    global sdk_instance
    sdk_instance = sdk
    print("✅ SDK instance injected into Orchestrator for inter-agent communication.")

async def handle_llm_and_calc_task(request_data, request):
    """
    这是一个编排任务的示例。
    它接收一个prompt，先让LLM Agent处理，然后用计算器Agent处理LLM的输出。
    """
    prompt = request_data.get("prompt")
    if not sdk_instance:
        return {"error": "Orchestrator is not properly configured."}
    if not prompt:
        return {"error": "Prompt is required."}

    print("\n🤖 Orchestrator: Received task. Starting coordination...")

    # --- 步骤 1: 调用 LLM Agent ---
    print("Orchestrator: Calling LLM Agent...")
    try:
        llm_response = await sdk_instance.invoke_agent_api(
            target_did="did:anp:llm_agent", # 确保你有一个使用此DID的llm_agent
            path="/llm/chat",
            method="POST",
            json_data={"prompt": f"Please extract the numbers from the following text and express them as a simple sum. For example, for 'I have 5 apples and 3 oranges', your output should be just '5+3'. Now, for the text '{prompt}', what is the mathematical expression?"}
        )
    except Exception as e:
        return {"error": f"Failed to call LLM Agent: {e}"}

    if not llm_response or "response" not in llm_response:
        return {"error": "Failed to get a valid response from LLM Agent."}

    math_expression = llm_response["response"].strip()
    print(f"Orchestrator: LLM Agent returned expression: '{math_expression}'")

    # --- 步骤 2: 解析并调用 Calculator Agent ---
    try:
        parts = math_expression.split('+')
        if len(parts) != 2:
            raise ValueError("Expression is not a simple sum.")
        a = int(parts[0].strip())
        b = int(parts[1].strip())

        print(f"Orchestrator: Calling Calculator Agent with a={a}, b={b}...")
        calc_response = await sdk_instance.invoke_agent_api(
            target_did="did:anp:calculator_agent", # 确保你有一个使用此DID的calculator_agent
            path="/calculator/add",
            method="POST",
            json_data={"a": a, "b": b}
        )

        final_result = calc_response.get("result")
        print(f"Orchestrator: Coordination complete. Final result: {final_result}")

        return {
            "task_summary": "Successfully orchestrated LLM and Calculator agents.",
            "llm_output": math_expression,
            "final_calculation": final_result
        }
    except Exception as e:
        return {"error": f"Failed to process the expression '{math_expression}'. Details: {e}"}

def register_abilities(agent):
    """注册总控自己的API"""
    agent.expose_api("/orchestrate/llm_and_calc", handle_llm_and_calc_task, methods=["POST"])
    print(f"✅ Injected 'orchestration' ability for agent: {agent.name}")