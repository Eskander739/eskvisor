from passlib.hash import bcrypt


class HashService:

    @staticmethod
    def hash_password(password: str, rounds: int = 14) -> str:

        # Проверяем на не-ASCII символы
        for i, char in enumerate(password):
            if ord(char) > 127:
                print(f"Не-ASCII символ на позиции {i}: {char} (код: {ord(char)})")

        rounds_dict = {"rounds": rounds}
        try:
            result = bcrypt.using(**rounds_dict).hash(password)
            print("Хеширование успешно")
            return result
        except Exception as e:
            print(f"Полная ошибка: {type(e).__name__}: {e}")
            raise

    @staticmethod
    def check_password(current_password: str, password_hash_for_check: str) -> bool:
        """
        Проверка пароля на соответствие
        :param current_password: текущий пароль
        :param password_hash_for_check: хэш пароля для проверки
        """
        return bcrypt.verify(current_password, password_hash_for_check)

    @staticmethod
    def generate_agent_credentials() -> tuple[str, str]:
        """
        Генерирует пару: agent_id и секретный ключ
        Возвращает: (agent_id, agent_secret)
        """
        # Уникальный ID агента (не секретный)
        agent_id = str(uuid.uuid4())

        # Секретный ключ - высокоэнтропийная случайная строка
        # Минимум 32 байта (256 бит) для безопасности
        agent_secret_bytes = secrets.token_bytes(256)
        agent_secret = base64.urlsafe_b64encode(agent_secret_bytes).decode("utf-8")

        return agent_id, agent_secret


if __name__ == "__main__":
    hh = HashService()
    print(hh.generate_agent_credentials())
