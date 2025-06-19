async def hello_handler(request_data, request):
    return {"msg": "hello from custom register!"}

async def info_handler(request_data, request):
    return {"msg": "info from custom register!"}