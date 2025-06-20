from utils.log_base import logger

async def add(a: float, b: float):
    try:
        result = float(a) + float(b)
        logger.info(f"  -> Calculator Agent: Performed {a} + {b} = {result}")
        return {"result": result}
    except (ValueError, TypeError) as e:
        return {"error": f"Invalid input for addition. Details: {e}"}

# 这个简单的Agent不需要初始化或清理，所以我们省略了这些函数