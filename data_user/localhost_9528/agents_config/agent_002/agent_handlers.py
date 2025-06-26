from starlette.responses import JSONResponse


async def hello_handler( request, message ):
    """
    这是一个打招呼的API，传入message参数即可返回问候语。
    """
    agent_name = request.state.agent.name
    return {
        "msg": f"{agent_name}的/hello接口收到请求:",
        "inbox": message
    }

async def info_handler(request_data, request):
    agent = getattr(request.state, "agent", None)
    return JSONResponse(
        content={
            "msg": f"{agent.name}的/info接口收到请求:",
            "param": request_data.get("params")
        },
        status_code=200
    )