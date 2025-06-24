# anp_open_sdk/agents_config/orchestrator_agent/agent_handlers.py

import httpx  # 需要安装 httpx: pip install httpx
import json

from anp_open_sdk.service.interaction.agent_api_call import agent_api_call_get
from anp_open_sdk.service.interaction.anp_tool import ANPToolCrawler
import logging
logger = logging.getLogger(__name__)
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.auth.auth_client import agent_auth_request
from anp_open_sdk_framework.local_methods.local_methods_caller import LocalMethodsCaller
from anp_open_sdk_framework.local_methods.local_methods_doc import LocalMethodsDocGenerator

# 在初始化时创建调用器
caller = None
# --- 模块级变量 ---
my_agent_instance = None

async def initialize_agent(agent, sdk_instance):
    """
    初始化钩子，创建和配置Agent实例，并附加特殊能力。
    """
    global my_agent_instance,caller
    logger.debug(f" -> Self-initializing Orchestrator Agent from its own module...")

    caller = LocalMethodsCaller(sdk_instance)

    # 关键步骤：将函数作为方法动态地附加到创建的 Agent 实例上
    agent.discover_and_describe_agents = discover_and_describe_agents
    agent.run_calculator_add_demo = run_calculator_add_demo
    agent.run_hello_demo = run_hello_demo
    agent.run_ai_crawler_demo = run_ai_crawler_demo
    agent.run_ai_root_crawler_demo = run_ai_root_crawler_demo
    agent.run_agent_002_demo = run_agent_002_demo
    agent.run_agent_002_demo_new = run_agent_002_demo_new
    logger.debug(f" -> Attached capability to loading side.")

    return my_agent_instance

async def discover_and_describe_agents(publisher_url):
    """
    发现并获取所有已发布Agent的详细描述。
    这个函数将被附加到 Agent 实例上作为方法。
    """
    logger.debug("\n🕵️  Starting agent discovery process (from agent method)...")



    async with httpx.AsyncClient() as client:
        try:
            # 1. 访问  获取公开的 agent 列表
            logger.debug("  - Step 1: Fetching public agent list...")
            response = await client.get(publisher_url)
            response.raise_for_status()
            data = response.json()
            agents = data.get("agents", [])
            logger.info(f"  - Found {len(agents)} public agents.")
            logger.info(f"\n  - {data}")
            for agent_info in agents:
                did = agent_info.get("did")
                if not did:
                    continue

                logger.debug(f"\n  🔎 Processing Agent DID: {did}")

                # 2. 获取每个 agent 的 DID Document
                user_id = did.split(":")[-1]
                host , port = ANPSDK.get_did_host_port_from_did(user_id)
                did_doc_url = f"http://{host}:{port}/wba/user/{user_id}/did.json"

                logger.debug(f"    - Step 2: Fetching DID Document from {did_doc_url}")
                status, did_doc_data, msg, success = await agent_auth_request(
                    caller_agent=my_agent_instance.id,  # 使用 self.id 作为调用者
                    target_agent=did,
                    request_url=did_doc_url
                )

                if not success:
                    logger.debug(f"    - ❌ Failed to get DID Document for {did}. Message: {msg}")
                    continue

                if isinstance(did_doc_data, str):
                    did_document = json.loads(did_doc_data)
                else:
                    did_document = did_doc_data

                # 3. 从 DID Document 中提取 ad.json 的地址并获取内容
                ad_endpoint = None
                for service in did_document.get("service", []):
                    if service.get("type") == "AgentDescription":
                        ad_endpoint = service.get("serviceEndpoint")
                        logger.info(f"\n   - ✅ get endpoint from did-doc{did}:{ad_endpoint}")
                        break

                if not ad_endpoint:
                    logger.debug(f"    - ⚠️  No 'AgentDescription' service found in DID Document for {did}.")
                    continue

                logger.debug(f"    - Step 3: Fetching Agent Description from {ad_endpoint}")
                status, ad_data, msg, success = await agent_auth_request(
                    caller_agent=my_agent_instance.id,
                    target_agent=did,
                    request_url=ad_endpoint
                )

                if success:
                    if isinstance(ad_data, str):
                        agent_description = json.loads(ad_data)
                    else:
                        agent_description = ad_data
                    logger.info(f"Agent Description:{ad_data}")
                    logger.debug("    - ✅ Successfully fetched Agent Description:")
                    logger.debug(json.dumps(agent_description, indent=2, ensure_ascii=False))
                else:
                    logger.debug(
                        f"    - ❌ Failed to get Agent Description from {ad_endpoint}. Status: {status}")

        except httpx.RequestError as e:
            logger.debug(f"  - ❌ Discovery process failed due to a network error: {e}")
        except Exception as e:
            logger.debug(f"  - ❌ An unexpected error occurred during discovery: {e}")




async def run_calculator_add_demo():

    caculator_did = "did:wba:localhost%3A9527:wba:user:28cddee0fade0258"
    calculator_agent = LocalAgent.from_did(caculator_did)
    # 构造 JSON-RPC 请求参数
    params = {
        "a": 1.23,
        "b": 4.56
    }

    result = await agent_api_call_get(
    my_agent_instance.id, calculator_agent.id, "/calculator/add", params  )

    logger.info(f"计算api调用结果: {result}")
    return result


async def run_hello_demo():
    target_did = "did:wba:localhost%3A9527:wba:user:5fea49e183c6c211"
    target_agent = LocalAgent.from_did(target_did)
    # 构造 JSON-RPC 请求参数
    params = {
        "message": "hello"
    }

    result = await agent_api_call_get(
    my_agent_instance.id, target_agent.id, "/hello", params  )

    logger.info(f"hello api调用结果: {result}")
    return result


async def run_ai_crawler_demo():

    target_did= "did:wba:localhost%3A9527:wba:user:28cddee0fade0258"


    crawler = ANPToolCrawler()

    # 协作智能体通过爬虫向组装后的智能体请求服务
    task_description = "我需要计算两个浮点数相加 2.88888+999933.4445556"

    host,port = ANPSDK.get_did_host_port_from_did(target_did)
    try:
        result = await crawler.run_crawler_demo(
            req_did=my_agent_instance.id,  # 请求方是协作智能体
            resp_did=target_did,  # 目标是组装后的智能体
            task_input=task_description,
            initial_url=f"http://{host}:{port}/wba/user/{target_did}/ad.json",
            use_two_way_auth=True,  # 使用双向认证
            task_type = "function_query"
        )
        logger.debug(f"智能调用结果: {result}")
        return

    except Exception as e:
        logger.info(f"智能调用过程中出错: {e}")
        return



async def run_ai_root_crawler_demo():

    target_did= "did:wba:localhost%3A9527:wba:user:28cddee0fade0258"


    crawler = ANPToolCrawler()

    # 协作智能体通过爬虫向组装后的智能体请求服务
    task_description = "我需要计算两个浮点数相加 2.88888+999933.4445556"

    host,port = ANPSDK.get_did_host_port_from_did(target_did)
    try:
        result = await crawler.run_crawler_demo(
            req_did=my_agent_instance.id,
            resp_did=target_did,
            task_input=task_description,
            initial_url="http://localhost:9527/publisher/agents",
            use_two_way_auth=True,  # 使用双向认证
            task_type = "root_query"
        )
        logger.debug(f"智能探索结果: {result}")
        return

    except Exception as e:
        logger.info(f"智能探索过程中出错: {e}")
        return



async def run_agent_002_demo(sdk, **kwargs):
    """调用 agent_002 上的自定义演示方法"""
    try:
        # 通过 sdk 获取 agent_002 实例
        target_agent = sdk.get_agent("did:wba:localhost%3A9527:wba:user:5fea49e183c6c211")
        if not target_agent:
            return "错误：未找到 agent_002"

        # 调用 agent_002 上的方法
        if hasattr(target_agent, 'demo_method') and callable(target_agent.demo_method):
            result = target_agent.demo_method()
            return result
        else:
            return "错误：在 agent_002 上未找到 demo_method"
            
    except Exception as e:
        logger.error(f"调用 agent_002.demo_method 失败: {e}")
        return f"调用 agent_002.demo_method 时出错: {e}"


async def run_agent_002_demo_new():
    """通过搜索调用 agent_002 的演示方法"""
    try:
        # 方式1：通过关键词搜索调用
        result = await caller.call_method_by_search("demo_method")
        logger.info(f"搜索调用结果: {result}")

        # 方式2：通过方法键直接调用
        result2 = await caller.call_method_by_key(
            "did:wba:localhost%3A9527:wba:user:5fea49e183c6c211::calculate_sum",
            10.5, 20.3
        )
        logger.info(f"直接调用结果: {result2}")

        return result

    except Exception as e:
        logger.error(f"调用失败: {e}")
        return f"调用时出错: {e}"


async def search_available_methods(keyword: str = ""):
    """搜索可用的本地方法"""
    results = LocalMethodsDocGenerator.search_methods(keyword=keyword)
    for result in results:
        print(f"🔍 {result['agent_name']}.{result['method_name']}: {result['description']}")
    return results


async def cleanup_agent():
    """
    清理钩子。
    """
    global my_agent_instance
    if my_agent_instance:
        logger.debug(f" -> Self-cleaning Orchestrator Agent: {my_agent_instance.name}")
        my_agent_instance = None
    logger.debug(f" -> Orchestrator Agent cleaned up.")