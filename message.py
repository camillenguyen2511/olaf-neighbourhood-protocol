import json
import base64
import os
from typing import List
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # for AES
from cryptography.hazmat.primitives import hashes


class Message:
    def __init__(self, content, message_type="chat", destination_servers=None):
        # assign the attributes
        self.content = content
        self.encrypted_content = None
        self.participants = []
        self.iv = None  # base64 encoded AES initialisation vector
        self.symm_keys = []
        self.counter = 0  # the nonce
        self.message_type = message_type

    # Function to encrypt the AES key
    def encrypt_key(self, receiver_public_key: rsa.RSAPublicKey, aes_key):
        encrypted_key = receiver_public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return base64.b64encode(encrypted_key).decode()

    # Decrypt the AES key
    def decrypt_key(self, aesKey):
        return self.private_key.decrypt(
            aesKey,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    # Encrypt message with AES key
    # Perform AES in GCM mode
    # Key length of 32 bytes (128 bits)
    def encrypt_chat_message(self, receiver_public_keys):
        # IV should be 16  bytes (randomly generated)
        self.iv = os.urandom(16)
        aes_key = os.urandom(32)

        chat_data = {"participants": self.participants, "message": self.content}
        chat_data_json = json.dumps(chat_data).encode()

        cipher = Cipher(algorithms.AES(aes_key), modes.GCM(self.iv))
        encryptor = cipher.encryptor()
        self.encrypted_content = encryptor.update(chat_data_json) + encryptor.finalize()

        for public_key in receiver_public_keys:
            encrypted_aes_key = self.encrypt_key(public_key, aes_key)
            self.symm_keys.append(encrypted_aes_key)

    # Decrypt message with AES key
    def decrypt_chat_message(self, key: bytes):
        cipher = Cipher(algorithms.AES(key), modes.GCM(self.iv))
        decryptor = cipher.decryptor()
        decrypted_content = (
            decryptor.update(self.encrypted_content.encode()) + decryptor.finalize()
        )
        return decrypted_content.decode()

    def prepare_chat_message(
        self,
        recipient_public_keys: List[rsa.RSAPublicKey],
        destination_servers,
        participants: List[str] = [],
    ):
        """Prepare an encrypted chat message, including AES key encryption."""

        # Encrypt the message and generate keys
        self.encrypt_chat_message(recipient_public_keys)

        chat_message = {
            "type": "chat",
            "destination_servers": destination_servers,
            "iv": base64.b64encode(self.iv).decode(),
            "symm_keys": self.symm_keys,
            "chat": base64.b64encode(self.encrypted_content).decode(),
        }

        return json.dumps(chat_message, indent=2)
