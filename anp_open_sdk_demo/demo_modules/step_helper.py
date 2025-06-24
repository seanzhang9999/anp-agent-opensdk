import json
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))  # 根据需要调整路径深度
sys.path.append(project_root)

from colorama import init, Fore, Style
from anp_open_sdk.utils.log_base import  logging as logger
from anp_open_sdk.config import get_global_config

init()  # 初始化colorama


class DemoStepHelper:
    """演示步骤辅助工具"""
    
    def __init__(self, step_mode: bool = False):
        self.step_mode = step_mode

    def pause(self, step_name: str = "", step_id: str = None):
        """暂停执行，等待用户确认"""
        if step_id is not None:
            step_name = self._load_helper_text(step_id=step_id)

        if self.step_mode:
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} "
                  f"{Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")

    @staticmethod
    def _load_helper_text(step_id: str, lang: str = None) -> str:
        """从helper.json加载帮助文本"""
        if lang is None:
            lang = dynamic_config.get("anp_sdk.helper_lang", "zh")

        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        helper_file = os.path.join(current_dir, 'anp_open_sdk_demo/helper.json')

        try:
            with open(helper_file, 'r', encoding='utf-8') as f:
                helper_data = json.load(f)
            return helper_data.get(str(step_id), {}).get(lang, "")
        except Exception as e:
            logger.error(f"读取帮助文件时发生错误: {e}")
            return ""