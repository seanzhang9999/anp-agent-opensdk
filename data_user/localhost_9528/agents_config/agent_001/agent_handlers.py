from starlette.responses import JSONResponse


async def hello_handler( request,request_data):
    agent = getattr(request.state, "agent", None)
    return JSONResponse(
        content={
            "msg": f"{agent.name}的/hello接口收到请求:",
            "param": request_data.get("params")
        },
        status_code=200
    )

async def info_handler(request, request_data):
    agent = getattr(request.state, "agent", None)
    return JSONResponse(
        content={
            "msg": f"{agent.name}的/info接口收到请求:",
            "param": request_data.get("params")
        },
        status_code=200
    )