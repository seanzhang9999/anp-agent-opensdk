## 奇怪问题
https://github.com/seanzhang9999/anp-agent-openchat/commit/0ab97301b7ca8515283fc9f4433a4944148d5b2d
遇到一个奇怪的问题
auth_middleware 中 auth_middleware callnext返回时 
定位不到异常，直接报告 错误: 'dict' object has no attribute 'strip'
最终定位到 \agent_connect\authentication\did_wba_auth_header.py 中
    def _get_domain(self, server_url: str) -> str:
被调用时，传入的server_url有时候是Request对象，不是str 导致了异常
    增加了对传入类型的判断后似乎问题消失

## 当前log
anp_llmagent开发：一条命令创建并启动agent-did ok
anp_llmapp开发：一条命令连接agent的过程 ok

修整 anp_llmapp代码 简化llm命令，考虑如何实现 
1. 用户 在chat中进入和远程agent对话模式，例如 #agent-id 进入远程对话模式
2. 用户 通过搜索agent 获得适当的远程agent的url存入bookmark
3. 用户 双向验证远程agent的真实性 考虑简化为消息中附加挑战要求对方agent回复签名验证以及中间加密 两边都能用（get post socket） 
修整 anp_llmagent代码 
1. 用户问题可以通过agent的思考，连接其他agent，获得答案后转发回来
2. 用户的问题可以通过agent的思考，发起多方群聊，优先考虑基于http直接做，反正各方都有resp和req，设计对应接口即可

考虑封装 anp_llmagent / anp_llmapp的web前端


## 计划工作

anp_llmagent 搭建
    封装更好的接口 方便各种agent框架集成——尤其是消息事件
    支持anp双向验证did 建立加密通道/多方wschat
    支持mcp接口调用本地功能对外anp服务
    支持动态开放多个anp能力接口
    支持对接flow事件和MultiAgent框架，将anp通信传入传出
mcp接口服务的web hosting
anp自身份与其他用户身份管理发布
未来示例以 anp_llmapp/mcp 与 anp_llmagent互联为主要场景
通讯加密问题——post/get和websocket下如何加密，能否不依赖域名和https

## 问题与bug

1. 当前版本
    Trae 调 sse mcp 连接消息发送失败， 启用mcp dev stdio 消息发送失败
    Trae stdio 客户端测试比较正常 也会偶发服务器问题
    猜想问题出在resp的服务启动上概率大
    Claude使用绝对路径python调用stdio可以启动 
        已通过增加printmute 解决print导致的mcp调用问题
        但是启动stdio时还报错log只读