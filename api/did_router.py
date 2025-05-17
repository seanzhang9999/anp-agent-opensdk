"""
DID document API router.
"""
import os
import json
import logging
from typing import Dict, Optional
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException
from config import dynamic_config
from core.config import settings

router = APIRouter(tags=["did"])


@router.get("/wba/user/{user_id}/did.json", summary="Get DID document")
async def get_did_document(user_id: str) -> Dict:
    """
    Retrieve a DID document by user ID.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dict: DID document
    """
    # 构建DID文档路径
    current_dir = Path(__file__).parent.parent.absolute()
    did_path = dynamic_config.get('demo_autorun.user_did_path')
    did_path = current_dir.joinpath( did_path,f"user_{user_id}" , "did_document.json" )



    if not did_path.exists():
        raise HTTPException(status_code=404, detail=f"DID document not found for user {user_id}")
    
    # 加载DID文档
    try:
        with open(did_path, 'r', encoding='utf-8') as f:
            did_document = json.load(f)
        return did_document
    except Exception as e:
        logging.error(f"Error loading DID document: {e}")
        raise HTTPException(status_code=500, detail="Error loading DID document")



@router.get("/agents/example/ad.json", summary="Get agent description")
async def get_agent_description() -> Dict:
    """
    Get agent description document.
    
    Returns:
        Dict: Agent description
    """

    description = "An example agent implementing DID WBA authentication"
    if os.environ.get("description"):
        description = os.getenv("description")

    return {
        "id": "example-agent-123",
        "name": "DID WBA Example Agent",
        "description": f"{description}",
        "version": "0.1.0",
        "capabilities": [
            "did-wba-authentication",
            "token-authentication"
        ],
        "endpoints": {
            "auth": "/auth/did-wba",
            "verify": "/auth/verify",
            "test": "/wba/test",
            "nlp": "/wba/anp-nlp",
        },
        "owner": "DID WBA Example",
        "created_at": "2025-04-21T00:00:00Z"
    }
