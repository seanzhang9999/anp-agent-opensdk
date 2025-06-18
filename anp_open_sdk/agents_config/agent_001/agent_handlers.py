async def hello_handler(request_data, request):
    return {"msg": "hello from agent 001"}

async def info_handler(request_data, request):
    return {"msg": "info from agent 001"}