import os
import time
import asyncio
from anp_sdk import ANPSDK, LocalAgent, RemoteAgent, get_did_host_port_from_did



from loguru import logger
from config.dynamic_config import dynamic_config


# 测试主函数
async def main():
    # 创建ANP SDK实例
    anp = ANPSDK()

    @anp.expose_api("api/test", methods=["GET"])
    def api_test(param: str = "test_value"):
        return {"result": f"收到参数: {param}"}

    @anp.expose_api("api/greeting")
    async def greeting(name: str = "World"):
        return {"message": f"Hello, {name}!"}

    @anp.register_message_handler("text")
    def handle_text_message(message):
        logger.info(f"收到文本消息: {message['content']}")
        return {"status": "received"}
    
    # 启动服务器
    server_result = anp.start_server()
    logger.info(f"服务器启动结果: {server_result}")
    
    # 等待服务器完全启动
    await asyncio.sleep(0.5)
    
    input("按任意键继续...")
    
    try:
        # 获取目标DID
        target_did = "did:wba:localhost:9527:wba:user:7c15257e086afeba"
        
        # 发送消息
        logger.info(f"发送消息到 {target_did}")
        response = await anp.send_message(target_did, "Hello from ANP SDK!")
        logger.info(f"消息发送响应: {response}")
        
        # 调用API
        logger.info(f"调用API: {target_did}/api/test")
        api_response = anp.call_api(target_did, "api/test", {"param": "test_value"})
        logger.info(f"API调用响应: {api_response}")
        
        # 等待一段时间以便查看结果
        await asyncio.sleep(5)
    finally:
        # 停止服务器
        stop_result = anp.stop_server()
        logger.info(f"服务器停止结果: {stop_result}")






if __name__ == "__main__":
    asyncio.run(main())