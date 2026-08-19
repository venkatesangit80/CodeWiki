import os
import uuid
import json
import logging
import asyncio
import httpx
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Graceful NATS importing (HAS_LIB pattern)
try:
    import nats
    from nats.errors import TimeoutError as NatsTimeoutError
    HAS_NATS = True
except ImportError:
    HAS_NATS = False

class BaseLLMClient(ABC):
    def __init__(self, config: Any):
        self.config = config

    @abstractmethod
    async def generate_completion(self, system_prompt: str, user_prompt: str) -> str:
        """Generates a text completion based on system and user prompts."""
        pass

class HTTPCompletionsClient(BaseLLMClient):
    def __init__(self, config: Any):
        super().__init__(config)
        self.client = AsyncOpenAI(
            base_url=self.config.llm.endpoint,
            api_key=os.environ.get("OPENAI_API_KEY", "dummy-local-key")
        )

    async def generate_completion(self, system_prompt: str, user_prompt: str) -> str:
        model = self.config.llm.model
        temp = self.config.llm.temperature
        
        logger.info(f"Calling HTTP LLM endpoint ({self.config.llm.endpoint}) with model {model}")
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temp,
                max_tokens=4000
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Error calling HTTP LLM: {e}")
            return f"Error calling HTTP LLM: {e}"

class NatsCompletionsClient(BaseLLMClient):
    async def generate_completion(self, system_prompt: str, user_prompt: str) -> str:
        if not HAS_NATS:
            logger.error("NATS library (nats-py) is not installed. Cannot use NATS LLM provider.")
            return "NATS LLM provider failed: nats-py library not installed."

        nats_url = os.getenv("NATS_SERVER_URL", self.config.llm.endpoint)
        user = os.getenv("NATS_USER", self.config.llm.nats_user)
        password = os.getenv("NATS_PASSWORD", self.config.llm.nats_password)
        
        # Open Bao/Vault integration override for LLM Config
        try:
            from app.storage.vault_integration import is_vault_enabled, refresh_and_read
            if is_vault_enabled():
                vault_env = os.environ.get('CLOUD_VAULT_ENV', 'production')
                vault_realm = os.environ.get('VAULT_REALM', 'teksecur')
                # First try realm specific configuration
                vault_config = refresh_and_read(f"{vault_env}/{vault_realm}/ai/config")
                if not vault_config:
                    # Fall back to common configuration
                    vault_config = refresh_and_read(f"{vault_env}/common/ai/config")
                if vault_config:
                    nats_url = vault_config.get("NATS_SERVER_URL") or nats_url
                    user = vault_config.get("NATS_USER") or user
                    password = vault_config.get("NATS_PASSWORD") or password
        except Exception:
            pass
            
        logger.info(f"Connecting to NATS broker at {nats_url}")
        
        try:
            nc = await nats.connect(
                servers=[nats_url],
                user=user,
                password=password,
                connect_timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to connect to NATS broker: {e}")
            return f"NATS connection failure: {e}"

        task_id = str(uuid.uuid4())
        request_subject = "llm.request.ops"
        response_subject = f"llm.results.{task_id}"
        
        logger.info(f"Subscribing to response subject: {response_subject}")
        response_text = ""
        
        try:
            # Subscribe to the response channel
            sub = await nc.subscribe(response_subject)
            
            full_prompt = f"{system_prompt}\n\nUser Prompt:\n{user_prompt}"
            
            payload = {
                "task_id": task_id,
                "prompt": full_prompt,
                "context": {
                    "vault_realm": "bfsi",
                    "org_id": "bfsi",
                    "temperature": self.config.llm.temperature,
                    "max_tokens": 4000,
                    "source": "codedoc-generator",
                    "enable_thinking": False,
                },
                "stream": False,
                "timestamp": str(uuid.uuid1()),
            }
            
            logger.info(f"Publishing request payload to NATS subject: {request_subject}")
            await nc.publish(request_subject, json.dumps(payload).encode())
            
            # Read single response message containing type=COMPLETED or type=FAILED
            while True:
                try:
                    msg = await sub.next_msg(timeout=180.0) # 3 minutes timeout
                    data = json.loads(msg.data.decode())
                    msg_type = data.get("type")
                    
                    if msg_type == "COMPLETED":
                        payload_data = data.get("payload", {})
                        if isinstance(payload_data, dict):
                            response_text = (
                                payload_data.get("response_text")
                                or payload_data.get("text")
                                or payload_data.get("response")
                                or payload_data.get("response_summary")
                                or payload_data.get("content")
                                or ""
                            )
                        elif isinstance(payload_data, str):
                            response_text = payload_data
                        break
                    elif msg_type == "FAILED":
                        logger.error(f"vLLM NATS worker returned failure: {data.get('error')}")
                        response_text = f"LLM Generation Failed: {data.get('error')}"
                        break
                except NatsTimeoutError:
                    logger.error("NATS subscription read timeout")
                    response_text = "Error: Timeout waiting for NATS LLM response"
                    break
                    
            await sub.unsubscribe()
        except Exception as e:
            logger.error(f"Error during NATS LLM execution: {e}")
            response_text = f"\n[NATS Execution Error: {e}]"
        finally:
            await nc.close()
            logger.info("Closed NATS connection")

        return response_text

class PythonFallbackClient(BaseLLMClient):
    async def generate_completion(self, system_prompt: str, user_prompt: str) -> str:
        logger.info("Bypassing external LLM call. Generating programmatic structured design documentation.")
        return "[Programmatic Fallback Generation Complete]"
