import os
import json
import secrets
from pathlib import Path
from anp_open_sdk.utils.log_base import  logging as logger
import socket

class DIDManager:
    """DID管理器，用于处理DID文档的存储和管理"""
    
    def __init__(self, hosted_dir: str = None):
        """
        初始化DID管理器
        
        Args:
            hosted_dir: DID托管目录路径，如果为None则使用默认路径
        """
        self.hosted_dir = Path(hosted_dir or os.environ.get('ANP_USER_HOSTED_PATH', 'anp_open_sdk/anp_users_hosted'))
        self.hosted_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取主机配置
        self.hostname = socket.gethostname()
        self.hostip = socket.gethostbyname(self.hostname)
        self.hostport = os.environ.get('HOST_DID_PORT', '9527')
        self.hostdomain = os.environ.get('HOST_DID_DOMAIN', 'localhost')
    
    def is_duplicate_did(self, did_document: dict) -> bool:
        """
        检查DID是否已存在
        
        Args:
            did_document: DID文档
            
        Returns:
            bool: 是否存在重复的DID
        """
        def _get_did_id(did_document):
            if isinstance(did_document, str):  # 可能是 JSON 字符串
                try:
                    did_document = json.loads(did_document)  # 解析 JSON
                except json.JSONDecodeError:
                    return None  # 解析失败，返回 None
            if isinstance(did_document, dict):  # 确保是字典
                return did_document.get('id')  # 取值
            return None


        did_id = _get_did_id(did_document)
        if not did_id:
            return False
            
        for user_req in self.hosted_dir.glob('user_*/did_document_request.json'):
            try:
                with open(user_req, 'r', encoding='utf-8') as f:
                    req_doc = json.load(f)
                if req_doc.get('id') == did_id:
                    return True
            except Exception as e:
                logger.error(f"读取DID文档失败: {e}")
        return False
    
    def store_did_document(self, did_document: dict) -> tuple[bool, str, str]:
        """
        存储DID文档
        
        Args:
            did_document: DID文档
            
        Returns:
            tuple: (是否成功, 新的DID ID, 错误信息)
        """
        try:
            # 生成新的sid
            sid = secrets.token_hex(8)
            user_dir = self.hosted_dir / f"user_{sid}"
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存原始请求
            req_path = user_dir / 'did_document_request.json'
            with open(req_path, 'w', encoding='utf-8') as f:
                json.dump(did_document, f, ensure_ascii=False, indent=2)
            
            # 修改DID文档
            modified_doc = self._modify_did_document(did_document.copy(), sid)
            
            # 保存修改后的文档
            did_path = user_dir / 'did_document.json'
            with open(did_path, 'w', encoding='utf-8') as f:
                json.dump(modified_doc, f, ensure_ascii=False, indent=2)
                
            return True, modified_doc, ""
            
        except Exception as e:
            error_msg = f"存储DID文档失败: {e}"
            logger.error(error_msg)
            return False, "", error_msg
    
    def _modify_did_document(self, did_document: dict, sid: str) -> dict:
        """
        修改DID文档，更新主机信息和ID
        
        Args:
            did_document: 原始DID文档
            sid: 新的会话ID
            
        Returns:
            dict: 修改后的DID文档
        """
        old_id = did_document['id']
        parts = old_id.split(':')
        
        if len(parts) > 3:
            # 更新主机和端口部分
            parts[2] = f"{self.hostdomain}%3A{self.hostport}"
            # 将user替换为hostuser
            for i in range(len(parts)):
                if parts[i] == "user":
                    parts[i] = "hostuser"
            parts[-1] = sid
            new_id = ':'.join(parts)
            did_document['id'] = new_id
            
            # 更新相关字段
            def replace_all_old_id(did_document, old_id, new_id):
                #递归遍历整个 DID 文档，替换所有出现的 old_id
                if isinstance(did_document, dict):  # 处理字典
                    return {
                        key: replace_all_old_id(value, old_id, new_id)
                        for key, value in did_document.items()
                    }
                elif isinstance(did_document, list):  # 处理列表
                    return [replace_all_old_id(item, old_id, new_id) for item in did_document]
                elif isinstance(did_document, str):  # 处理字符串
                    return did_document.replace(old_id, new_id)
                else:
                    return did_document  # 其他类型不变
            # 全局替换所有 `old_id`
            did_document = replace_all_old_id(did_document, old_id, new_id)
    
                        
        return did_document 