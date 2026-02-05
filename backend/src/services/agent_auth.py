import hmac
import hashlib
import secrets
import time
import json
import uuid
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ProductionAgentAuthManager:

    def __init__(self, cache_client, secret_storage):
        """
        :param cache_client: Redis или другой кеш для nonce
        :param secret_storage: Хранилище зашифрованных секретов
        """
        self.cache = cache_client
        self.secret_storage = secret_storage
        self.time_window = 300  # 5 минут в секундах

    @staticmethod
    def generate_agent_credentials() -> tuple[str, str]:
        """
        Генерирует новые учетные данные для агента
        Возвращает: (agent_id, agent_secret)
        """
        # ID агента (публичный)
        agent_id = f"agent-{uuid.uuid4()}"

        # Секретный ключ (256 бит энтропии)
        agent_secret = secrets.token_urlsafe(32)  # 32 байта в URL-safe base64

        return agent_id, agent_secret

    def create_signed_request(
        self,
        agent_id: str,
        agent_secret: str,
        payload: Dict,
        timestamp: Optional[int] = None,
        nonce: Optional[str] = None,
    ) -> Dict:
        """
        Создает подписанный запрос для отправки агентом
        """
        if timestamp is None:
            timestamp = int(time.time())

        if nonce is None:
            nonce = str(uuid.uuid4())

        # Создаем подпись
        signature = self._create_signature(
            agent_id=agent_id,
            agent_secret=agent_secret,
            timestamp=timestamp,
            nonce=nonce,
            payload=payload,
        )

        return {
            "headers": {
                "X-Agent-ID": agent_id,
                "X-Agent-Timestamp": str(timestamp),
                "X-Agent-Nonce": nonce,
                "X-Agent-Signature": signature,
                "Content-Type": "application/json",
            },
            "payload": payload,
        }

    def _create_signature(
        self,
        agent_id: str,
        agent_secret: str,
        timestamp: int,
        nonce: str,
        payload: Dict,
    ) -> str:
        """
        Внутренний метод создания подписи
        """
        # Каноническая сериализация payload
        canonical_payload = self._canonical_serialize(payload)

        # Создаем строку для подписи
        message = f"{agent_id}:{timestamp}:{nonce}:{canonical_payload}"

        # HMAC-SHA256
        return hmac.new(
            agent_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _canonical_serialize(data: Dict) -> str:
        """
        Каноническая сериализация JSON для детерминированной подписи
        """
        return json.dumps(data, separators=(",", ":"), sort_keys=True)

    def verify_request(
        self, agent_id: str, signature: str, timestamp: str, nonce: str, payload: Dict
    ) -> tuple[bool, str]:
        """
        Проверяет запрос агента
        Возвращает: (успех, сообщение об ошибке)
        """
        try:
            # 1. Проверка формата
            if not all([agent_id, signature, timestamp, nonce]):
                return False, "Missing required headers"

            timestamp_int = int(timestamp)

            # 2. Проверка временного окна
            current_time = int(time.time())
            time_diff = abs(current_time - timestamp_int)

            if time_diff > self.time_window:
                return False, f"Timestamp out of window. Diff: {time_diff}s"

            # 3. Проверка повторного использования nonce
            if self._is_nonce_used(agent_id, nonce):
                return False, "Nonce already used"

            # 4. Получение секрета агента
            agent_secret = self.secret_storage.get_decrypted_secret(agent_id)
            if not agent_secret:
                return False, "Agent not found or inactive"

            # 5. Проверка подписи
            expected_signature = self._create_signature(
                agent_id=agent_id,
                agent_secret=agent_secret,
                timestamp=timestamp_int,
                nonce=nonce,
                payload=payload,
            )

            if not hmac.compare_digest(expected_signature, signature):
                return False, "Invalid signature"

            # 6. Регистрируем использованный nonce
            self._register_nonce_usage(agent_id, nonce)

            logger.info(f"Successful authentication for agent: {agent_id}")
            return True, "Success"

        except ValueError as e:
            logger.warning(f"Invalid request format: {e}")
            return False, "Invalid request format"
        except Exception as e:
            logger.error(f"Error verifying request: {e}")
            return False, "Internal server error"

    def _is_nonce_used(self, agent_id: str, nonce: str) -> bool:
        """
        Проверяет, использовался ли уже этот nonce
        """
        cache_key = f"nonce:{agent_id}:{nonce}"
        return bool(self.cache.get(cache_key))

    def _register_nonce_usage(self, agent_id: str, nonce: str):
        """
        Регистрирует использование nonce
        """
        cache_key = f"nonce:{agent_id}:{nonce}"
        self.cache.setex(
            cache_key, self.time_window * 2, "1"
        )  # Двойное окно на всякий случай


# if __name__ == "__main__":
#     agent_id = str(uuid.uuid4())
#     agent_secret = str(uuid.uuid4())
#     agent_auth = ProductionAgentAuthManager()
#     print(agent_auth.create_hmac_signature(agent_id=agent_id, agent_secret=agent_secret))
