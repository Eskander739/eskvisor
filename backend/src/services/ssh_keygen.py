import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.constants import KEY_DIR

from src.constants import KEY_NAME


class SSHKeyGenerator:
    """Класс для генерации SSH ключей"""

    def __init__(self, key_name=KEY_NAME, key_dir=KEY_DIR):
        self.key_name = key_name
        self.key_dir = os.path.expanduser(key_dir)
        self.private_key_path = os.path.join(self.key_dir, key_name)
        self.public_key_path = f"{self.private_key_path}.pub"

        # Создаем директорию если её нет
        os.makedirs(self.key_dir, exist_ok=True)

    def generate_ed25519_key(self, passphrase=None):
        """Генерация пары ключей Ed25519"""

        # Генерация приватного ключа
        private_key = ed25519.Ed25519PrivateKey.generate()

        # Настройка шифрования (опционально)
        if passphrase:
            encryption = serialization.BestAvailableEncryption(
                passphrase.encode("utf-8")
            )
        else:
            encryption = serialization.NoEncryption()

        # Сериализация приватного ключа
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption,
        )

        # Получение публичного ключа
        public_key = private_key.public_key()
        public_openssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )

        return private_pem, public_openssh

    def save_keys(self, private_pem, public_openssh):
        """Сохранение ключей в файлы"""

        # Сохранение приватного ключа
        with open(self.private_key_path, "wb") as f:
            f.write(private_pem)

        # Установка прав доступа 600 (только владелец)
        os.chmod(self.private_key_path, stat.S_IRUSR | stat.S_IWUSR)

        # Форматирование публичного ключа для SSH
        ssh_public_key = f"{public_openssh.decode('utf-8').strip()}"

        # Сохранение публичного ключа
        with open(self.public_key_path, "w") as f:
            f.write(ssh_public_key)

        return self.private_key_path, self.public_key_path

    def generate_and_save(self, passphrase=None):
        """Генерация и сохранение ключей"""
        if not Path(self.private_key_path).exists():
            private_pem, public_openssh = self.generate_ed25519_key(passphrase)
            return self.save_keys(private_pem, public_openssh)
        return None


# Пример использования
if __name__ == "__main__":
    # Создание генератора ключей
    generator = SSHKeyGenerator()

    # Генерация ключей (с парольной фразой или без)
    # private_path, public_path = generator.generate_and_save()  # Без пароля
    private_path, public_path = generator.generate_and_save()

    print(f"Приватный ключ сохранен: {private_path}")
    print(f"Публичный ключ сохранен: {public_path}")
    #
    # # Показать публичный ключ для копирования
    # generator.print_public_key_for_copy()
    #
    # # Проверка ключей
    # print("\nПроверка содержимого файлов:")
    # print("-" * 30)
    # with open(private_path, "r") as f:
    #     print(f"Приватный ключ (первые 3 строки):")
    #     for i, line in enumerate(f):
    #         if i < 3:
    #             print(f"  {line.strip()}")
    #
    # with open(public_path, "r") as f:
    #     print(f"\nПубличный ключ:")
    #     print(f"  {f.read().strip()}")
