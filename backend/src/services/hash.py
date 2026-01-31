from passlib.hash import bcrypt


class HashService:

    @staticmethod
    def hash_password(password: str, rounds: int = 14) -> str:
        # Отладочная информация
        print(f"Получен пароль: {repr(password)}")
        print(f"Длина в символах: {len(password)}")
        print(f"Длина в байтах: {len(password.encode('utf-8'))}")

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


if __name__ == "__main__":
    hh = HashService()
    print(hh.hash_password("12345"))