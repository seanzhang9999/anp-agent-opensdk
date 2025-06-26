import os
import yaml
from openai import AsyncOpenAI
from anp_open_sdk.anp_sdk_agent import LocalAgent

# --- 模块级变量，代表这个Agent实例的状态 ---
# 这些变量在模块被加载时创建，并贯穿整个应用的生命周期
my_agent_instance = None
my_llm_client = None


async def initialize_agent(agent, sdk_instance):
    """
    初始化钩子，现在由插件自己负责创建和配置Agent实例。
    它不再接收参数，而是返回创建好的agent实例。
    """
    global my_agent_instance, my_llm_client

    print(f"  -> Self-initializing LLM Agent from its own module...")


    # 1. 使用传入的 agent 实例
    my_agent_instance = agent

    # __file__ 是当前文件的路径
    config_path = os.path.join(os.path.dirname(__file__), "agent_mappings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    my_agent_instance.name = cfg["name"]
    print(f"  -> Self-created agent instance: {my_agent_instance.name}")

    # 3. 创建并存储LLM客户端作为模块级变量
    api_key = os.getenv("OPENAI_API_KEY", "your_default_key_if_not_set")
    base_url = os.getenv("OPENAI_BASE_URL")
    my_llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    print(f"  -> Self-created LLM client.")

    # 4. 自己注册自己的API
    # 注意：现在是直接在模块内调用实例的方法
    my_agent_instance.expose_api("/llm/chat", chat_completion, methods=["POST"])
    print(f"  -> Self-registered '/llm/chat' ability.")

    # 5. 将创建和配置好的agent实例返回给加载器
    return my_agent_instance


async def cleanup_agent():
    """
    清理钩子，现在也直接使用模块级变量。
    """
    global my_llm_client
    if my_llm_client:
        print(f"  -> Self-cleaning LLM Agent: Closing client...")
        await my_llm_client.close()
        print(f"  -> LLM client cleaned up.")


async def chat_completion(prompt: str ):
    """
    API处理函数，现在直接使用模块内的 my_llm_client。
    它不再需要从request中获取agent实例。
    """
    global my_llm_client
    if not prompt:
        return {"error": "Prompt is required."}
    if not my_llm_client:
        return {"error": "LLM client is not initialized in this module."}
    try:
        print(f"  -> LLM Agent Module: Sending prompt to model...")
        response = await my_llm_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        message_content = response.choices[0].message.content
        return {"response": message_content}
    except Exception as e:
        print(f"  -> ❌ LLM Agent Module Error: {e}")
        return {"error": f"An error occurred: {str(e)}"}