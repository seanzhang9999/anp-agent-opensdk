import logging
logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, status
from anp_user_service.app.models.schemas import ChatAgentRequest, ChatResponse, LLMConfig
from anp_user_service.app.services.user_service import get_user_personal_data_path
from anp_user_service.app.services.llm_service import get_llm_response_with_rag
from anp_open_sdk.config import config
router = APIRouter()

@router.post("/chat/agent", response_model=ChatResponse)
async def chat_with_personal_agent(request: ChatAgentRequest):
    if not request.username and not request.did:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username or DID must be provided.")

    personal_data_path = get_user_personal_data_path(username=request.username, did=request.did)

    if not personal_data_path or not personal_data_path.exists():
        # Fallback to a non-RAG response or inform the user
        # For now, let's try to proceed but context will be minimal
        logger.debug(f"Warning: Personal data path not found for user. RAG context will be limited. Path: {personal_data_path}")
        # Or, return an error if personal_data is essential:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personal data for user not found.")

    # Get API key from environment variables via settings

    api_key = config.secrets.openai_api_key
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key is not configured on the server."
        )
    
    from pydantic import HttpUrl

    llm_config = LLMConfig(
        apiBase=HttpUrl(f"http://{config.anp_user_service.api_base}"),  # 必须是 http(s):// 开头的有效URL
        apiKey=api_key,
        model=config.anp_user_service.model_name
    )



    reply, error = await get_llm_response_with_rag(
        user_message=request.message,
        personal_data_path=personal_data_path, # Will be None if not found, handled in service
        llm_config=llm_config
    )

    if error:
        # You might want to log the error server-side
        logger.debug(f"Error in agent chat: {error}")
        # Return a more generic error to the client for some cases
        return ChatResponse(success=False, message="Error processing your request with the agent.", error=error)
    
    if reply:
        return ChatResponse(success=True, reply=reply)
    else:
        return ChatResponse(success=False, message="Agent could not generate a reply.", error="No reply from LLM.")
