import json
from typing import Dict, List, Optional
from pathlib import Path
from .local_methods_decorators import LOCAL_METHODS_REGISTRY

class LocalMethodsDocGenerator:
    """本地方法文档生成器"""

    @staticmethod
    def generate_methods_doc(output_path: str = "local_methods_doc.json"):
        """生成所有本地方法的文档"""
        doc = {
            "generated_at": str(Path().absolute()),
            "total_methods": len(LOCAL_METHODS_REGISTRY),
            "methods": LOCAL_METHODS_REGISTRY.copy()
        }

        # 保存到文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        print(f"📚 已生成本地方法文档: {output_path}")
        return doc

    @staticmethod
    def search_methods(keyword: str = "", agent_name: str = "", tags: List[str] = None) -> List[Dict]:
        """搜索本地方法"""
        results = []

        for method_key, method_info in LOCAL_METHODS_REGISTRY.items():
            # 关键词匹配
            if keyword and keyword.lower() not in method_info["name"].lower() and \
               keyword.lower() not in method_info["description"].lower():
                continue

            # Agent名称匹配
            if agent_name and agent_name.lower() not in method_info["agent_name"].lower():
                continue

            # 标签匹配
            if tags and not any(tag in method_info["tags"] for tag in tags):
                continue

            results.append({
                "method_key": method_key,
                "agent_did": method_info["agent_did"],
                "agent_name": method_info["agent_name"],
                "method_name": method_info["name"],
                "description": method_info["description"],
                "signature": method_info["signature"],
                "tags": method_info["tags"]
            })

        return results

    @staticmethod
    def get_method_info(method_key: str) -> Optional[Dict]:
        """获取指定方法的详细信息"""
        return LOCAL_METHODS_REGISTRY.get(method_key)