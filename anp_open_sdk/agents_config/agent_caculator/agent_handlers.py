# anp_open_sdk/agents_config/calculator_agent/agent_handlers.py

async def add(request_data, request):
    """一个简单的加法处理器"""
    try:
        a = float(request_data.get("a", 0))
        b = float(request_data.get("b", 0))
        result = a + b
        print(f"  -> Calculator Agent: Performed {a} + {b} = {result}")
        return {"result": result}
    except (ValueError, TypeError) as e:
        return {"error": f"Invalid input for addition. Details: {e}"}

# 这个简单的Agent不需要初始化或清理，所以我们省略了这些函数