#!/usr/bin/env python3
"""
ANP Tool 智能爬虫演示 - 优化版本
使用 ANP 协议进行智能体信息爬取，通过大模型自主决定爬取路径

主要功能:
1. 创建本地Python代码生成智能体
2. 配置智能体API接口
3. 使用智能爬虫调用本地智能体
4. 使用智能爬虫调用外部Web智能体
5. 演示智能体间的协作
"""

import os
import asyncio
import shutil
import sys
import json
import time
from urllib.parse import quote

import yaml
from anyio import Path
from dotenv import load_dotenv
from fastapi import Request
from anp_open_sdk.utils.log_base import  logging as logger
from starlette.responses import JSONResponse

# 加载环境变量
load_dotenv()

# 添加项目路径到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from anp_open_sdk.config.legacy.dynamic_config import dynamic_config
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.service.interaction.anp_tool import CustomJSONEncoder, ANPToolCrawler
from anp_sdk_demo.services.sdk_manager import DemoSDKManager


# ============================================================================
# 主要功能函数 - 简化版本
# ============================================================================

async def create_python_agent(sdk: ANPSDK):
    """创建Python代码生成智能体"""
    logger.debug("步骤1: 创建Python代码生成智能体")

    from anp_open_sdk.anp_sdk_user_data import did_create_user

    # 创建临时用户参数
    temp_user_params = {
        'name': 'Python任务智能体',
        'host': 'localhost',
        'port': 9527,
        'dir': 'wba',
        'type': 'user'
    }

    # 创建DID文档
    did_document = did_create_user(temp_user_params)
    if not did_document:
        logger.error("智能体创建失败")
        return None

    logger.debug(f"智能体创建成功，DID: {did_document['id']}")

    # 创建LocalAgent实例并注册
    python_agent = LocalAgent.from_did(did_document['id'])
    sdk.register_agent(python_agent)
    logger.debug(f"智能体 {python_agent.name} 注册成功")
    
    return python_agent


def register_agent_api_handlers(sdk: ANPSDK, python_agent: LocalAgent):
    """为Python智能体注册API处理函数"""
    logger.debug("步骤2: 注册API处理函数")
    
    @python_agent.expose_api("/tasks/send", methods=["POST"])
    async def task_receive(request_data, request: Request):
        """处理代码生成请求"""
        start = time.time()
        
        # 检查请求方法
        if request.method == "GET":
            return JSONResponse({"error": "GET method not allowed"}, status_code=405)
            
        try:
            # 验证请求格式
            if request.headers.get("Content-Type") != "application/json":
                return JSONResponse({"error": "请求必须是 JSON 格式"}, status_code=400)
                
            # 检查请求体
            raw_data = await request.body()
            if not raw_data:
                return JSONResponse({"error": "请求体为空"}, status_code=400)
                
            # 解析请求
            body = await request.json()
            message = extract_message_from_body(body)
            
            if not message:
                return JSONResponse({"error": "Missing 'message' field"}, status_code=400)
                
            logger.debug(f"收到代码生成请求: {message}")
            
            # 调用LLM生成代码
            code_response = await call_llm(message)
            code = extract_code_from_response(code_response)
            
            logger.debug("代码生成完成")
            
            # 构建响应
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"code": code}
            }
            
            return JSONResponse(json.loads(json.dumps(response)), status_code=200)
            
        except Exception as e:
            logger.error(f"任务处理失败: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
            
        finally:
            logger.debug(f"任务耗时: {time.time() - start:.2f}s")


async def configure_agent_interfaces(python_agent: LocalAgent):
    """配置智能体API和接口描述"""
    logger.debug("步骤3: 配置智能体接口")

    from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

    # 获取用户目录
    success, did_doc, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
    if not success:
        logger.error("无法获取用户目录")
        return False
        
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    user_full_path = os.path.join(user_dirs, user_dir)
    
    # 创建接口配置
    agent_id = f"http://localhost:9527/wba/user/{python_agent.id}/ad.json"
    
    # 创建智能体描述文档
    agent_description = create_agent_description(python_agent, agent_id)
    
    # 创建API接口描述
    api_interface = create_api_interface()
    
    # 创建JSON-RPC接口描述
    jsonrpc_interface = create_jsonrpc_interface()
    
    # 保存配置文件
    await save_interface_files(user_full_path, agent_description, api_interface, jsonrpc_interface)
    
    logger.debug("智能体接口配置完成")
    return True


def create_agent_description(python_agent: LocalAgent, agent_id: str):
    """创建智能体描述文档"""
    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "did": "https://w3id.org/did#",
            "ad": "https://agent-network-protocol.com/ad#"
        },
        "@type": "ad:AgentDescription",
        "@id": agent_id,
        "name": f"ANPSDK Agent{python_agent.name}",
        "did": python_agent.id,
        "owner": {
            "@type": "Organization",
            "name": "code-writer.local",
            "@id": python_agent.id
        },
        "description": "代码生成智能体，可根据自然语言请求生成 Python 示例代码。",
        "version": "1.0.0",
        "created": "2025-05-25T20:00:00Z",
        "endpoint": f"http://localhost:9527/agent/api/{quote(python_agent.id)}/tasks/send",
        "ad:securityDefinitions": {
            "didwba_sc": {
                "scheme": "didwba",
                "in": "header",
                "name": "Authorization"
            }
        },
        "ad:security": "didwba_sc",
        "ad:AgentDescription": [],
        "ad:interfaces": [
            {
                "@type": "ad:NaturalLanguageInterface",
                "protocol": "JSON",
                "url": f"http://localhost:9527/wba/user/{quote(python_agent.id)}/codegen-interface.json",
                "description": "自然语言代码生成接口的 JSON 描述"
            }
        ]
    }


def create_api_interface():
    """创建API接口描述"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Code Writer Agent API",
            "version": "1.0.0"
        },
        "paths": {
            "/tasks/send": {
                "post": {
                    "summary": "基于自然语言生成代码的服务,在post请求的body部分添加message参数,说明生成代码需求,服务将自动返回结果",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "生成的代码",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "code": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_jsonrpc_interface():
    """创建JSON-RPC接口描述"""
    return {
        "jsonrpc": "2.0",
        "summary": "基于自然语言生成代码的服务,在post请求的body部分添加message参数,说明生成代码需求,服务将自动返回结果",
        "method": "generate_code",
        "params": {
            "message": {
                "type": "string",
                "value": "用 Python 生成冒泡排序"
            }
        },
        "result": {
            "code": {
                "type": "string"
            }
        },
        "meta": {
            "openapi": "3.0.0",
            "info": {
                "title": "Code Writer Agent API",
                "version": "1.0.0"
            },
            "httpMethod": "POST",
            "endpoint": "/tasks/send"
        }
    }


async def save_interface_files(user_full_path: str, agent_description: dict, 
                             api_interface: dict, jsonrpc_interface: dict):
    """保存接口配置文件"""
    # 保存智能体描述文件
    template_ad_path = Path(user_full_path) / "template-ad.json"
    template_ad_path = Path(UnifiedConfig.resolve_path(template_ad_path.as_posix()))
    await template_ad_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_ad_path, 'w', encoding='utf-8') as f:
        json.dump(agent_description, f, ensure_ascii=False, indent=2)
    logger.debug(f"智能体描述文件已保存: {template_ad_path}")

    # 保存YAML接口文件
    template_yaml_path = Path(user_full_path) / "codegen-interface.yaml"
    template_yaml_path = Path(UnifiedConfig.resolve_path(template_yaml_path.as_posix()))
    await template_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_yaml_path, "w", encoding="utf-8") as file:
        yaml.dump(api_interface, file, allow_unicode=True)
    logger.debug(f"YAML接口文件已保存: {template_yaml_path}")

    # 保存JSON-RPC接口文件
    template_jsonrpc_path = Path(user_full_path) / "codegen-interface.json"
    template_jsonrpc_path = Path(UnifiedConfig.resolve_path(template_jsonrpc_path.as_posix()))
    await template_jsonrpc_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_jsonrpc_path, "w", encoding="utf-8") as file:
        json.dump(jsonrpc_interface, file, indent=2, ensure_ascii=False)
    logger.debug(f"JSON-RPC接口文件已保存: {template_jsonrpc_path}")


async def run_crawler_demo(crawler: ANPToolCrawler, target_agent: LocalAgent,
                           task_input: str, output_file: str = "crawler_result.json"):
    """运行爬虫演示 - 基本版本"""
    logger.debug(f"开始爬虫演示: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=None,
        resp_did=target_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.debug(f"爬取结果已保存到 {output_file}")
    
    return result


async def run_crawler_demo_with_different_agent(crawler: ANPToolCrawler,
                                                target_agent: LocalAgent,
                                                sdk: ANPSDK, task_input: str):
    """使用不同智能体身份运行爬虫演示"""
    logger.debug(f"使用不同智能体身份运行爬虫演示: {task_input}")
    
    # 获取另一个智能体
    user_data = sdk.user_data_manager.get_user_data_by_name("本田")
    if not user_data:
        logger.warning("未找到'本田'智能体，跳过此演示")
        return None
        
    agent1 = LocalAgent.from_did(user_data.did)

    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=agent1.id,
        resp_did=target_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    output_file = "demo_data/agent1_crawler_result.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.debug(f"爬取结果已保存到 {output_file}")
    
    return result


async def run_web_agent_crawler_demo(crawler: ANPToolCrawler,
                                     task_input: str = "查询北京天津上海今天的天气",
                                     initial_url: str = "https://agent-search.ai/ad.json"):
    """运行Web智能体爬虫演示 - 来自project_1的功能"""
    logger.debug(f"开始Web智能体爬虫演示: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=initial_url,
        use_two_way_auth=True,
        req_did=None,
        resp_did=None,
        task_type="weather_query"
    )
    
    # 保存结果到文件
    output_file = "demo_data/project2_web_agent_crawler_result.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.debug(f"Web智能体爬取结果已保存到 {output_file}")
    
    return result


async def cleanup_resources(sdk: ANPSDK, python_agent: LocalAgent):
    """清理临时资源"""
    logger.debug("步骤6: 清理临时资源")
    
    try:
        from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

        # 获取用户目录
        success, _, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
        if not success:
            logger.error("无法找到用户目录")
            return
            
        # 从SDK注销智能体
        sdk.unregister_agent(python_agent.id)
        logger.debug(f"智能体 {python_agent.name} 已从SDK注销")
        
        # 删除用户目录
        user_dirs = dynamic_config.get('anp_sdk.user_did_path')
        user_full_path = os.path.join(user_dirs, user_dir)
        
        if os.path.exists(user_full_path):
            shutil.rmtree(user_full_path)
            logger.debug(f"用户目录已删除: {user_full_path}")
            
    except Exception as e:
        logger.error(f"清理资源时发生错误: {e}")


# ============================================================================
# 辅助函数
# ============================================================================

def extract_message_from_body(body: dict):
    """从请求体中提取message字段"""
    def find_message(data):
        """递归查找 'message' 值"""
        if isinstance(data, dict):
            if "message" in data:
                return data["message"]
            for value in data.values():
                result = find_message(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = find_message(item)
                if result:
                    return result
        return None
        
    return find_message(body)


def extract_code_from_response(response):
    """从LLM响应中提取代码内容"""
    if isinstance(response, dict):
        return json.dumps(response)
    elif hasattr(response, "content"):
        return response.content
    elif hasattr(response, "__dict__"):
        return json.dumps(response.__dict__)
    return str(response)


async def call_llm(prompt: str):
    """调用LLM生成代码"""
    try:
        llm_client = create_llm_client()
        if not llm_client:
            return "# [错误] 无法创建LLM客户端"
            
        model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4")

        messages = [
            {"role": "system", "content": "你是一个擅长写 Python 代码的助手"},
            {"role": "user", "content": prompt}
        ]

        completion = await llm_client.chat.completions.create(
            model=model_name,
            messages=messages
        )

        response_message = completion.choices[0].message
        return response_message
        
    except Exception as e:
        logger.error(f"模型服务调用失败: {e}")
        return "# [错误] 无法生成代码"


def create_llm_client():
    """创建LLM客户端"""
    try:
        model_provider = os.environ.get("MODEL_PROVIDER", "openai").lower()
        if model_provider == "openai":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        )
            return client
        else:
            logger.error("需要配置OpenAI")
            return None

    except Exception as e:
        logger.error(f"创建LLM客户端失败: {e}")
        return None


# ============================================================================
# 主函数 - 清晰的流程展示
# ============================================================================

async def main():
    """
    主函数：演示ANP智能爬虫与本地/Web智能体交互的完整流程
    
    核心步骤:
    1. 创建并初始化SDK
    2. 创建本地Python代码生成智能体
    3. 配置智能体API和接口描述
    4. 启动服务并运行爬虫演示
    5. 运行Web智能体爬虫演示
    6. 清理资源
    """
    logger.debug("=== ANP智能爬虫演示开始 ===")
    
    # 步骤1: 初始化SDK
    logger.debug("步骤1: 初始化ANP SDK")
    sdk = ANPSDK()
    
    # 步骤2: 创建Python代码生成智能体
    python_agent = await create_python_agent(sdk)
    if not python_agent:
        logger.error("智能体创建失败，退出演示")
        return
    
    # 步骤3: 注册API服务函数
    register_agent_api_handlers(sdk, python_agent)
    
    # 步骤4: 配置智能体接口
    success = await configure_agent_interfaces(python_agent)
    if not success:
        logger.error("智能体接口配置失败，退出演示")
        return
    
    # 步骤5: 启动服务
    logger.debug("步骤4: 启动ANP服务")
    sdk_manager = DemoSDKManager()
    sdk_manager.start_server(sdk)
    
    # 步骤6: 创建并运行爬虫演示
    logger.debug("步骤5: 运行智能爬虫演示")
    crawler = ANPToolCrawler()
    
    try:
        # 演示1: 基本爬虫功能 - 生成冒泡排序代码
        logger.debug("\n=== 演示1: 本地智能体 - 基本爬虫功能 ===")
        await run_crawler_demo(
            crawler, 
            python_agent, 
            "写个冒泡法排序代码",
            "demo_data/agent_anptool_crawler_result.json"
        )
        
        # 演示2: 使用不同智能体身份 - 生成随机数代码
        logger.debug("\n=== 演示2: 本地智能体 - 使用不同智能体身份 ===")
        await run_crawler_demo_with_different_agent(
            crawler, 
            python_agent, 
            sdk, 
            "写个随机数生成代码"
        )
        
        # 演示3: Web智能体爬虫演示 - 来自project_1的功能
        logger.debug("\n=== 演示3: Web智能体 - 天气查询功能 ===")
        await run_web_agent_crawler_demo(
            crawler,
            "查询北京天津上海今天的天气",
            "https://agent-search.ai/ad.json"
        )
        
        logger.debug("\n=== 所有演示完成 ===")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 步骤7: 清理资源
        await cleanup_resources(sdk, python_agent)
        logger.debug("=== ANP智能爬虫演示结束 ===")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())