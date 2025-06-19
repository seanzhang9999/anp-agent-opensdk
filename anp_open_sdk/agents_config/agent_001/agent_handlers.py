# plugins/llm_agent/handlers.py
import os
from openai import AsyncOpenAI


# 这个agent现在需要存储自己的状态（llm_client）

async def initialize_agent(agent):
    """
    初始化钩子：创建并存储一个可复用的OpenAI客户端。
    """
    print(f"  -> Initializing LLM Agent: Creating OpenAI client...")

    # 从环境变量中获取API密钥和基础URL（推荐做法）
    # 你需要先设置这些环境变量:
    # export OPENAI_API_KEY="your_api_key"
    # export OPENAI_BASE_URL="your_base_url" (如果使用本地或第三方模型)
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        print("  -> ⚠️ Warning: OPENAI_API_KEY environment variable not set. LLM Agent may not work.")

    # 创建异步的OpenAI客户端实例
    # 这个实例管理着与OpenAI服务器的HTTP连接池（类似aiohttp.ClientSession）
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
        # AsyncOpenAI 客户端也支持关闭其内部的 httpx.AsyncClient
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
        print(f"  -> LLM Agent: Sending prompt to model: '{prompt[:30]}...'")
        response = await agent.llm_client.chat.completions.create(
            model="gpt-3.5-turbo",  # 或者你使用的任何模型
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )

        message_content = response.choices[0].message.content
        return {"response": message_content}

    except Exception as e:
        print(f"  -> ❌ LLM Agent Error: {e}")
        return {"error": f"An error occurred while communicating with the LLM: {str(e)}"}


def register_abilities(agent):
    """注册API，这部分不变"""
    agent.expose_api("/llm/chat", chat_completion, methods=["POST"])
    print(f"✅ Injected 'chat_completion' ability for agent: {agent.name}")

async def hello_handler(request_data, request):
    return {"msg": "hello from agent 001"}

async def info_handler(request_data, request):
    return {"msg": "info from agent 001"}