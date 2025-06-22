import imaplib
import email
import os
import json
import smtplib
import socks
from email.mime.text import MIMEText
from email.header import Header
from anp_open_sdk.utils.log_base import  logging as logger

class MailManager:
    """邮箱管理器，用于处理DID托管请求的邮件操作"""
    
    def __init__(self):
        self.mail_user = os.environ.get('HOSTER_MAIL_USER')
        self.mail_pass = os.environ.get('HOSTER_MAIL_PASSWORD')
        
        if not (self.mail_user and self.mail_pass):
            raise ValueError('请在环境变量中配置 HOSTER_MAIL_USER/HOSTER_MAIL_PASSWORD')
            
        # 设置 SOCKS5 代理
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 1080)
        socks.wrapmodule(imaplib)
    
    def connect_imap(self):
        """连接到IMAP服务器"""
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(self.mail_user, self.mail_pass)
        return imap
    
    def send_reply_email(self, to_address: str, subject: str, content: str):
        """发送回复邮件"""
        try:
            content = json.dumps(content, ensure_ascii=False, indent=2)
            reply = MIMEText(content, 'plain', 'utf-8')
            reply['Subject'] = Header(subject)
            reply['From'] = self.mail_user
            reply['To'] = to_address
            smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            smtp.login(self.mail_user, self.mail_pass)
            smtp.sendmail(self.mail_user, [to_address], reply.as_string())
            smtp.quit()
            return True
        except Exception as e:
            logger.error(f"发送回复邮件失败: {e}")
            return False
    
    def get_unread_did_requests(self):
        """获取未读的DID托管请求邮件"""
        imap = self.connect_imap()
        imap.select('INBOX')
        subject = "ANP-DID host request"
        
        status, messages = imap.search(None, f'(UNSEEN SUBJECT "{subject}")')
        if status != 'OK':
            imap.logout()
            return []
            
        msg_ids = messages[0].split()
        requests = []
        
        for num in msg_ids:
            status, data = imap.fetch(num, '(RFC822)')
            if status != 'OK':
                continue
                
            msg = email.message_from_bytes(data[0][1])
            body = None
            
            # 解析邮件正文
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset)
                        break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset)
                
            if not body:
                continue
                
            try:
                did_document = json.loads(body)
                requests.append({
                    'message_id': num,
                    'from_address': msg['From'],
                    'did_document': did_document
                })
            except Exception as e:
                logger.error(f"解析DID文档失败: {e}")
                
        imap.logout()
        return requests
    
    def mark_message_as_read(self, message_id):
        """将邮件标记为已读"""
        try:
            imap = self.connect_imap()
            imap.select('INBOX')
            imap.store(message_id, '+FLAGS', '\\Seen')
            imap.logout()
            return True
        except Exception as e:
            logger.error(f"标记邮件为已读失败: {e}")
            return False 