import logging
logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Optional
import httpx

from ..models.schemas import LLMConfig

async def get_llm_response_with_rag(
    user_message: str,
    personal_data_path: Path,
    llm_config: LLMConfig
) -> tuple[Optional[str], Optional[str]]:
    """
    Generates LLM response using RAG from personal_data directory.
    Returns (reply, error_message)
    """
    context = "Relevant information from your personal data:\n\n"
    try:
        if personal_data_path.exists() and personal_data_path.is_dir():
            for file_path in personal_data_path.iterdir():
                if file_path.is_file():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        context += f"--- Content from {file_path.name} ---\n{content}\n\n"
                    except Exception as e:
                        context += f"--- Could not read {file_path.name}: {str(e)} ---\n\n"
        else:
            context += "No personal data files found or accessible.\n"
    except Exception as e:
        context += f"Error accessing personal data directory: {str(e)}\n"

    final_prompt = f"{context}\n--- User's question ---\nUser: {user_message}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_config.apiKey}"
    }
    payload = {
        "model": llm_config.model,
        "messages": [{"role": "user", "content": final_prompt}],
        # Add other parameters like temperature, max_tokens if needed
        # "stream": False # For simplicity, not using streaming here
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.debug(f"start llm{payload}" )
            response = await client.post(
                str(llm_config.apiBase).rstrip('/') + "/chat/completions", # Common path
                json=payload,
                headers=headers,
                timeout=60.0 # Increased timeout for LLM calls
            )

        response.raise_for_status() # Will raise an exception for 4XX/5XX responses
        data = response.json()
        logger.debug(f"get llm response {data}")
        
        if data.get("choices") and len(data["choices"]) > 0:
            reply = data["choices"][0].get("message", {}).get("content")
            if reply:
                return reply, None
            else:
                return None, "LLM response format error: No content in message."
        else:
            return None, f"LLM API did not return choices. Response: {data}"

    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        return None, f"LLM API request failed with status {e.response.status_code}: {error_body}"
    except httpx.RequestError as e:
        return None, f"LLM API request error: {str(e)}"
    except Exception as e:
        return None, f"Error during LLM call: {str(e)}"
