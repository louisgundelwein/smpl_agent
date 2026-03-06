"""Credential encryption utilities using Fernet symmetric encryption."""

import os
from cryptography.fernet import Fernet


class EncryptionManager:
    """Manages credential encryption with automatic key generation and rotation.

    On first use, generates a key and stores it at the configured path.
    Subsequent uses load the existing key.
    """

    def __init__(self, key_path: str) -> None:
        """Initialize encryption manager.

        Args:
            key_path: Path where encryption key is stored.
        """
        self.key_path = key_path
        self._cipher = None

    def _load_or_generate_key(self) -> None:
        """Load existing key or generate and save a new one."""
        if self._cipher is not None:
            return

        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(self.key_path) or ".", exist_ok=True)
            with open(self.key_path, "wb") as f:
                f.write(key)
            # Restrict permissions on key file
            os.chmod(self.key_path, 0o600)

        self._cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted string (base64-encoded).
        """
        self._load_or_generate_key()
        encrypted = self._cipher.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string.

        Args:
            ciphertext: The encrypted string to decrypt.

        Returns:
            Decrypted plaintext string.
        """
        self._load_or_generate_key()
        decrypted = self._cipher.decrypt(ciphertext.encode())
        return decrypted.decode()

    def is_encrypted(self, value: str) -> bool:
        """Check if a value looks like it's encrypted (base64 with gAAAAA prefix).

        Args:
            value: The value to check.

        Returns:
            True if value appears to be Fernet-encrypted.
        """
        return value.startswith("gAAAAA")
