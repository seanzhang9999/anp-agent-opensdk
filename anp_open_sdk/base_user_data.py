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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANP用户工具

这个程序提供了ANP用户管理的基本功能：
1. 创建新用户 (-n)
2. 列出所有用户 (-l)
3. 按服务器信息排序显示用户 (-s)
"""

from typing import Dict, List, Optional, Any

from abc import ABC, abstractmethod

class BaseUserData(ABC):

    @property
    @abstractmethod
    def did_doc_path(self) -> str:
        pass
    @property
    @abstractmethod
    def did_private_key_file_path(self) -> str:
        pass

    @abstractmethod
    def get_did(self) -> str: ...
    @abstractmethod
    def get_private_key_path(self) -> str: ...
    @abstractmethod
    def get_public_key_path(self) -> str: ...
    @abstractmethod
    def get_token_to_remote(self, remote_did: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def store_token_to_remote(self, remote_did: str, token: str, expires_delta: int): ...
    @abstractmethod
    def get_token_from_remote(self, remote_did: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def store_token_from_remote(self, remote_did: str, token: str): ...
    @abstractmethod
    def add_contact(self, contact: Dict[str, Any]): ...
    @abstractmethod
    def get_contact(self, remote_did: str) -> Optional[Dict[str, Any]]: ...
    @abstractmethod
    def list_contacts(self) -> List[Dict[str, Any]]: ...

class BaseUserDataManager(ABC):
    @abstractmethod
    def get_user_data(self, did: str) -> Optional[BaseUserData]: ...
    @abstractmethod
    def get_all_users(self) -> List[BaseUserData]: ...
    @abstractmethod
    def get_user_data_by_name(self, name: str) -> Optional[BaseUserData]: ...
