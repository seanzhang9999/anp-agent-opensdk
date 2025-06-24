# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from anp_open_sdk.config import get_global_config
import json
import time
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import Header
from typing import List, Dict, Tuple
from pathlib import Path
from anp_open_sdk.utils.log_base import  logging as logger
from abc import ABC, abstractmethod
from anp_open_sdk.config import get_global_config

class MailBackend(ABC):
    """邮件后端抽象基类"""
    
    @abstractmethod
    def send_email(self, to_address: str, subject: str, content: str, from_address: str = None) -> bool:
        """发送邮件"""
        pass
    
    @abstractmethod
    def get_unread_emails(self, subject_filter: str = None) -> List[Dict]:
        """获取未读邮件"""
        pass
    
    @abstractmethod
    def mark_as_read(self, message_id: str) -> bool:
        """标记邮件为已读"""
        pass


class LocalFileMailBackend(MailBackend):
    """本地文件邮件后端，用于测试"""
    
    def __init__(self, mail_dir: str = None):
        self.mail_dir = Path(mail_dir or "./local_mail_storage")
        self.mail_dir.mkdir(exist_ok=True)
        
        # 创建子目录
        (self.mail_dir / "inbox").mkdir(exist_ok=True)
        (self.mail_dir / "sent").mkdir(exist_ok=True)
        (self.mail_dir / "read").mkdir(exist_ok=True)
    
    def send_email(self, to_address: str, subject: str, content: str, from_address: str = None) -> bool:
        """发送邮件到本地文件"""
        try:
            timestamp = int(time.time() * 1000)
            filename = f"{timestamp}_{to_address.replace('@', '_at_')}.json"
            
            email_data = {
                "message_id": str(timestamp),
                "from_address": from_address or "test@local.com",
                "to_address": to_address,
                "subject": subject,
                "content": content,
                "timestamp": timestamp,
                "read": False
            }
            
            # 保存到发件箱
            sent_path = self.mail_dir / "sent" / filename
            with open(sent_path, 'w', encoding='utf-8') as f:
                json.dump(email_data, f, ensure_ascii=False, indent=2)
            
            # 同时保存到收件箱
            inbox_path = self.mail_dir / "inbox" / filename
            with open(inbox_path, 'w', encoding='utf-8') as f:
                json.dump(email_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"本地邮件已发送: {subject} -> {to_address}")
            return True
            
        except Exception as e:
            logger.error(f"发送本地邮件失败: {e}")
            return False
    
    def get_unread_emails(self, subject_filter: str = None) -> List[Dict]:
        """获取未读邮件"""
        try:
            unread_emails = []
            inbox_dir = self.mail_dir / "inbox"
            
            for email_file in inbox_dir.glob("*.json"):
                try:
                    with open(email_file, 'r', encoding='utf-8') as f:
                        email_data = json.load(f)
                    
                    if not email_data.get("read", False):
                        if subject_filter is None or subject_filter in email_data.get("subject", ""):
                            unread_emails.append(email_data)
                            
                except Exception as e:
                    logger.warning(f"读取邮件文件失败 {email_file}: {e}")
            
            return sorted(unread_emails, key=lambda x: x.get("timestamp", 0))
            
        except Exception as e:
            logger.error(f"获取未读邮件失败: {e}")
            return []
    
    def mark_as_read(self, message_id: str) -> bool:
        """标记邮件为已读"""
        try:
            inbox_dir = self.mail_dir / "inbox"
            read_dir = self.mail_dir / "read"
            
            for email_file in inbox_dir.glob("*.json"):
                try:
                    with open(email_file, 'r', encoding='utf-8') as f:
                        email_data = json.load(f)
                    
                    if email_data.get("message_id") == message_id:
                        email_data["read"] = True
                        
                        # 移动到已读目录
                        read_path = read_dir / email_file.name
                        with open(read_path, 'w', encoding='utf-8') as f:
                            json.dump(email_data, f, ensure_ascii=False, indent=2)
                        
                        # 删除原文件
                        email_file.unlink()
                        
                        logger.debug(f"邮件已标记为已读: {message_id}")
                        return True
                        
                except Exception as e:
                    logger.warning(f"处理邮件文件失败 {email_file}: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"标记邮件为已读失败: {e}")
            return False
    
    def simulate_hosted_did_response(self, parent_did: str, host: str, port: str) -> bool:
        """模拟托管DID响应邮件"""
        response_content = f"""托管DID申请已批准

主机: {host}
端口: {port}
父DID: {parent_did}

请使用以下信息配置您的托管DID。"""
        
        return self.send_email(
            to_address="test@local.com",
            subject="ANP HOSTED DID RESPONSED",
            content=response_content,
            from_address="admin@local.com"
        )


class GmailBackend(MailBackend):
    """Gmail邮件后端"""
    
    def __init__(self):
        # 优先从 dynamic_config 获取配置，回退到环境变量
        config = get_global_config()
        if config.mail.hoster_mail_user is not None:
            self.mail_user = config.mail.hoster_mail_user
            self.mail_pass = config.secrets.hoster_mail_password
        else:
            self.mail_user =  config.mail.sender_mail_user
            self.mail_pass = config.secrets.sender_mail_password

        if not (self.mail_user and self.mail_pass):
            raise ValueError('请在环境变量中配置邮箱用户名和密码')
        
        # 配置SOCKS代理（如果需要）
        try:
            import socks
            socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 1080)
            socks.wrapmodule(imaplib)
            socks.wrapmodule(smtplib)
        except ImportError:
            pass
    
    def connect_imap(self):
        """连接到IMAP服务器"""
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(self.mail_user, self.mail_pass)
        return imap
    
    def send_email(self, to_address: str, subject: str, content: str, from_address: str = None) -> bool:
        """发送邮件"""
        try:
            msg = MIMEText(content, 'plain', 'utf-8')
            msg['Subject'] = Header(subject)
            msg['From'] = from_address or self.mail_user
            msg['To'] = to_address
            
            smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            smtp.login(self.mail_user, self.mail_pass)
            smtp.sendmail(self.mail_user, [to_address], msg.as_string())
            smtp.quit()
            
            logger.debug(f"邮件已发送: {subject} -> {to_address}")
            return True
            
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False
    
    def get_unread_emails(self, subject_filter: str = None) -> List[Dict]:
        """获取未读邮件"""
        try:
            imap = self.connect_imap()
            imap.select('INBOX')
            
            # 构建搜索条件
            search_criteria = 'UNSEEN'
            if subject_filter:
                search_criteria += f' SUBJECT "{subject_filter}"'
            
            status, messages = imap.search(None, f'({search_criteria})')
            
            if status != 'OK' or not messages or not messages[0]:
                imap.logout()
                return []
            
            msg_ids = messages[0].split()
            unread_emails = []
            
            for num in msg_ids:
                try:
                    status, data = imap.fetch(num, '(RFC822)')
                    if status == 'OK':
                        msg = email.message_from_bytes(data[0][1])
                        
                        # 解析邮件内容
                        if msg.is_multipart():
                            content = ""
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    charset = part.get_content_charset() or 'utf-8'
                                    content = part.get_payload(decode=True).decode(charset)
                                    break
                        else:
                            charset = msg.get_content_charset() or 'utf-8'
                            content = msg.get_payload(decode=True).decode(charset)
                        
                        unread_emails.append({
                            'message_id': num.decode(),
                            'from_address': msg['From'],
                            'subject': msg['Subject'],
                            'content': content,
                            'timestamp': time.time()
                        })
                        
                except Exception as e:
                    logger.warning(f"解析邮件失败 {num}: {e}")
            
            imap.logout()
            return unread_emails
            
        except Exception as e:
            logger.error(f"获取未读邮件失败: {e}")
            return []
    
    def mark_as_read(self, message_id: str) -> bool:
        """标记邮件为已读"""
        try:
            imap = self.connect_imap()
            imap.select('INBOX')
            imap.store(message_id, '+FLAGS', '\\Seen')
            imap.logout()
            return True
            
        except Exception as e:
            logger.error(f"标记邮件为已读失败: {e}")
            return False


class EnhancedMailManager:
    """增强的邮件管理器"""
    
    def __init__(self, use_local_backend: bool = False, local_mail_dir: str = None):
        """
        初始化邮件管理器
        
        Args:
            use_local_backend: 是否使用本地文件后端（用于测试）
            local_mail_dir: 本地邮件存储目录
        """
        logger.debug(f"使用本地文件邮件后端参数设置:{use_local_backend}")
        if use_local_backend:
            if local_mail_dir is None:
                config = get_global_config()

                local_mail_dir = config.mail.local_backend_path
            self.backend = LocalFileMailBackend(local_mail_dir)
            logger.debug("使用本地文件邮件后端")

        else:
            self.backend = GmailBackend()
            logger.debug("使用Gmail邮件后端")
    
    def send_email(self, to_address: str, subject: str, content: str, from_address: str = None) -> bool:
        """发送邮件"""
        return self.backend.send_email(to_address, subject, content, from_address)
    
    def send_reply_email(self, to_address: str, subject: str, content: str) -> bool:
        """发送回复邮件（兼容旧接口）"""
        return self.send_email(to_address, subject, content)
    
    def get_unread_did_requests(self) -> List[Dict]:
        """获取未读的DID请求邮件"""
        return self.backend.get_unread_emails("ANP-DID host request")
    
    def get_unread_hosted_responses(self) -> List[Dict]:
        """获取未读的托管DID响应邮件"""
        return self.backend.get_unread_emails("ANP HOSTED DID RESPONSED")
    
    def mark_message_as_read(self, message_id: str) -> bool:
        """标记邮件为已读"""
        return self.backend.mark_as_read(message_id)
    
    def send_hosted_did_request(self, did_document: dict, register_email: str = None) -> bool:
        """发送托管DID申请邮件"""
        
        try:
            config = get_global_config()
            body = json.dumps(did_document, ensure_ascii=False, indent=2)
            to_address = register_email or config.mail.register_mail_user
            from_address = config.mail.sender_mail_user


            logger.debug(f"发送托管DID申请邮件: {to_address}")
            return self.send_email(
                from_address=from_address,
                to_address=to_address,
                subject="ANP-DID host request",
                content=body
            )
            
        except Exception as e:
            logger.error(f"发送托管DID申请邮件失败: {e}")
            return False
    
    def simulate_hosted_did_response(self, parent_did: str, host: str, port: str) -> bool:
        """模拟托管DID响应（仅本地后端支持）"""
        if isinstance(self.backend, LocalFileMailBackend):
            return self.backend.simulate_hosted_did_response(parent_did, host, port)
        else:
            logger.warning("模拟托管DID响应仅在本地后端支持")
            return False


# 兼容性函数，保持向后兼容
class MailManager(EnhancedMailManager):
    """原MailManager类的兼容性包装"""
    
    def __init__(self):
        # 检查是否设置了测试模式
        from anp_open_sdk.config import get_global_config
        config = get_global_config()
        use_local = config.mail.use_local_backend
        super().__init__(use_local_backend=use_local)


# 测试工具函数
def create_test_mail_manager(mail_dir: str = None) -> EnhancedMailManager:
    """创建测试用的邮件管理器"""
    return EnhancedMailManager(use_local_backend=True, local_mail_dir=mail_dir)


def setup_test_environment(mail_dir: str = None) -> Tuple[EnhancedMailManager, Path]:
    """设置测试环境"""
    mail_manager = create_test_mail_manager(mail_dir)
    mail_storage_path = Path(mail_dir or "./local_mail_storage")
    
    # 创建一些测试邮件
    mail_manager.send_email(
        to_address="test@local.com",
        subject="测试邮件",
        content="这是一封测试邮件",
        from_address="sender@local.com"
    )
    
    logger.debug(f"测试环境已设置，邮件存储路径: {mail_storage_path}")
    return mail_manager, mail_storage_path


if __name__ == "__main__":
    # 测试代码
    logger.debug("测试邮件管理器...")
    
    # 创建测试环境
    test_manager, storage_path = setup_test_environment("./test_mail")
    
    # 测试发送邮件
    test_manager.send_email(
        to_address="test@local.com",
        subject="ANP-DID host request",
        content='{"id": "did:wba:test", "host": "localhost", "port": "9527"}'
    )
    
    # 测试获取未读邮件
    unread = test_manager.get_unread_did_requests()
    logger.debug(f"未读DID请求: {len(unread)}")
    
    # 测试模拟响应
    test_manager.simulate_hosted_did_response(
        parent_did="did:wba:test",
        host="localhost",
        port="9527"
    )
    
    # 测试获取响应邮件
    responses = test_manager.get_unread_hosted_responses()
    logger.debug(f"未读响应: {len(responses)}")
    
    logger.debug(f"测试完成，邮件存储在: {storage_path}")