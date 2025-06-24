import asyncio
from typing import Any, Dict, Optional, List

from .local_methods_decorators import LOCAL_METHODS_REGISTRY
from .local_methods_doc import LocalMethodsDocGenerator

class LocalMethodsCaller:
    """本地方法调用器"""

    def __init__(self, sdk):
        self.sdk = sdk
        self.doc_generator = LocalMethodsDocGenerator()

    async def call_method_by_search(self, search_keyword: str, *args, **kwargs) -> Any:
        """
        通过搜索关键词找到方法并调用

        Args:
            search_keyword: 搜索关键词
            *args, **kwargs: 方法参数
        """
        # 搜索方法
        results = self.doc_generator.search_methods(keyword=search_keyword)

        if not results:
            raise ValueError(f"未找到包含关键词 '{search_keyword}' 的方法")

        if len(results) > 1:
            method_list = [f"{r['agent_name']}.{r['method_name']}" for r in results]
            raise ValueError(f"找到多个匹配的方法: {method_list}，请使用更具体的关键词")

        # 调用找到的方法
        method_info = results[0]
        return await self.call_method_by_key(
            method_info["method_key"],
            *args, **kwargs
        )

    async def call_method_by_key(self, method_key: str, *args, **kwargs) -> Any:
        """
        通过方法键调用方法

        Args:
            method_key: 方法键 (格式: agent_did::method_name)
            *args, **kwargs: 方法参数
        """
        # 获取方法信息
        method_info = self.doc_generator.get_method_info(method_key)
        if not method_info:
            raise ValueError(f"未找到方法: {method_key}")

        # 获取目标agent
        target_agent = self.sdk.get_agent(method_info["agent_did"])
        if not target_agent:
            raise ValueError(f"未找到agent: {method_info['agent_did']}")

        # 获取方法
        method_name = method_info["name"]
        if not hasattr(target_agent, method_name):
            raise AttributeError(f"Agent {method_info['agent_name']} 没有方法 {method_name}")

        method = getattr(target_agent, method_name)
        if not callable(method):
            raise TypeError(f"{method_name} 不是可调用方法")

        # 调用方法
        print(f"🚀 调用方法: {method_info['agent_name']}.{method_name}")
        if method_info["is_async"]:
            return await method(*args, **kwargs)
        else:
            return method(*args, **kwargs)

    def list_all_methods(self) -> List[Dict]:
        """列出所有可用的本地方法"""
        return list(LOCAL_METHODS_REGISTRY.values())