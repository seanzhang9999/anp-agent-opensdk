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

"""
DID WBA configuration module with both client and server functionalities.
"""
import os
import secrets
from typing import List, Dict, Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parents[2] / ".env"
load_dotenv(dotenv_path=env_path)
logger.debug(f"{env_path}")




class Settings(BaseSettings):
    """DID WBA configuration settings."""
    
    ENV_PATH: Path = env_path

    class Config:
        """Pydantic configuration class."""
        case_sensitive = True


settings = Settings()


