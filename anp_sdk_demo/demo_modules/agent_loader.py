from typing import List, Optional
from loguru import logger
from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager
from anp_open_sdk.config.dynamic_config import dynamic_config


class DemoAgentLoader:
    """演示用Agent加载器"""
    
    @staticmethod
    def load_demo_agents(sdk: ANPSDK) -> List[LocalAgent]:
        """加载演示用的智能体"""
        user_data_manager: LocalUserDataManager = sdk.user_data_manager
        agent_cfg = dynamic_config.get('anp_sdk.agent', {})
        agent_names = [
            agent_cfg.get('demo_agent1'),
            agent_cfg.get('demo_agent2'),
            agent_cfg.get('demo_agent3')
        ]

        agents = []
        for agent_name in agent_names:
            if not agent_name:
                continue

            user_data = user_data_manager.get_user_data_by_name(agent_name)
            if user_data:
                agent = LocalAgent.from_name(agent_name)
                agents.append(agent)
            else:
                logger.warning(f'未找到预设名字={agent_name} 的用户数据')
        return agents

    @staticmethod
    def find_hosted_agent(sdk: ANPSDK, user_datas) -> Optional[LocalAgent]:
        """查找托管的智能体"""
        for user_data in user_datas:
            agent = LocalAgent(sdk, user_data.did)
            if agent.is_hosted_did:
                logger.info(f"hosted_did: {agent.id}")
                logger.info(f"parent_did: {agent.parent_did}")
                logger.info(f"hosted_info: {agent.hosted_info}")
                return agent
        return None

