import logging
logger = logging.getLogger(__name__)

async def add(a: float, b: float):
    try:
        result = float(a) + float(b)
        logger.info(f"  -> Calculator Agent: Performed {a} + {b} = {result}")
        return {"result": result}
    except (ValueError, TypeError) as e:
        params = {"a": 2.88888, "b": 999933.4445556}
        return {
            "error": f'use: {{"params": {params}}} 来调用'
        }
# 这个简单的Agent不需要初始化或清理，所以我们省略了这些函数