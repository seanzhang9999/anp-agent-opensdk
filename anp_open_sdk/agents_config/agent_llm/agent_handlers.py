# anp_open_sdk/agents_config/llm_agent/agent_handlers.py
import os
from openai import AsyncOpenAI

async def initialize_agent(agent):
    """
    初始化钩子：创建并存储一个可复用的OpenAI客户端。
    """
    print(f"  -> Initializing LLM Agent: Creating OpenAI client...")

    # 从环境变量中获取API密钥和基础URL（推荐做法）
    api_key = os.getenv("OPENAI_API_KEY", "your_default_key_if_not_set")
    base_url = os.getenv("OPENAI_API_BASE_URL") # 如果为None，则使用官方OpenAI

    if api_key == "your_default_key_if_not_set":
        print("  -> ⚠️ Warning: OPENAI_API_KEY environment variable not set. LLM Agent may not work.")

    agent.llm_client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    print(f"  -> LLM Agent Initialized.")

async def cleanup_agent(agent):
    """
    清理钩子：关闭OpenAI客户端的HTTP会话。
    """
    if hasattr(agent, 'llm_client'):
        print(f"  -> Cleaning up LLM Agent: Closing OpenAI client session...")
        await agent.llm_client.close()
        print(f"  -> LLM Agent Cleaned up.")

async def chat_completion(request_data, request):
    """
    这个handler使用初始化时创建的llm_client来与大模型交互。
    """
    prompt = request_data.get("prompt")
    if not prompt:
        return {"error": "Prompt is required."}

    # 假设ANPSDK将agent实例附加到请求对象上
    agent = request.get('agent')
    if not agent or not hasattr(agent, 'llm_client'):
        return {"error": "LLM client is not initialized."}

    try:
        print(f"  -> LLM Agent: Sending prompt to model: '{prompt[:50]}...'")
        response = await agent.llm_client.chat.completions.create(
            model="gpt-3.5-turbo", # 或者你使用的任何模型
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.0 # 为了让输出更稳定
        )

        message_content = response.choices[0].message.content
        return {"response": message_content}

    except Exception as e:
        print(f"  -> ❌ LLM Agent Error: {e}")
        return {"error": f"An error occurred while communicating with the LLM: {str(e)}"}

def register_abilities(agent):
    """
    这个函数是可选的，因为我们的主加载逻辑现在可以自动处理
    声明式的YAML映射。但保留它可以用于更复杂的注册场景。
    """
    agent.expose_api("/llm/chat", chat_completion, methods=["POST"])
    print(f"✅ Injected 'chat_completion' ability for agent: {agent.name}")