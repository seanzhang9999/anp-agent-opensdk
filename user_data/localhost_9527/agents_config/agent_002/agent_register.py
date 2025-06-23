
from anp_open_sdk.service.router.router_agent import wrap_business_handler


def register(agent):
    """
    自定义注册脚本：为 agent 注册任意 API、消息、事件等
    """
    from .agent_handlers import hello_handler, info_handler

    # 注册 /hello POST,GET
    agent.expose_api("/hello", wrap_business_handler(hello_handler), methods=["POST","GET"])

    # 注册 /info POST
    agent.expose_api("/info", info_handler, methods=["POST"])

    # 注册一个自定义消息处理器
    @agent.register_message_handler("text")
    async def custom_text_handler(msg):
        return {"reply": f"自定义注册收到消息: {msg.get('content')}"}

    # 你还可以注册事件、定时任务、权限校验等
    # agent.register_group_event_handler(...)
    # agent.add_permission_check(...)
    # ...
    
    
        # 注册一个自定义方法
    def demo_method():
        return f"这是来自 {agent.name} 的演示方法"
    agent.demo_method = demo_method

    print(f"[agent_register] 已为 {agent.name} 完成自定义注册")