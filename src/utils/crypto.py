"""Functions related to cryptography, including public key handling, signature, and fingerprint"""

import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


def generate_fingerprint(public_key: rsa.RSAPublicKey):
    """Generates a fingerprint based on the public key (hash)."""
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(public_bytes).hexdigest()


def load_pem_public_key(public_key_str: str):
    """Convert the PEM public key string into a `RSAPublicKey` object"""
    return serialization.load_pem_public_key(
        public_key_str.encode(), backend=default_backend()
    )


def export_public_key(public_key: rsa.RSAPublicKey):
    """Export the public key to PEM format"""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def sign_message(message: str, counter, private_key: rsa.RSAPrivateKey):
    """Returns the signature after signing the message"""
    # Sign the message using the RSA-PSS scheme
    # Signature should be Base64 of data + counter
    message_bytes = message.encode("utf-8") + str(counter).encode("utf-8")
    signature = private_key.sign(
        message_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def verify_signature(
    public_key: rsa.RSAPublicKey, signature: str, message: str, counter
):
    """Verify signature using sender's public key and the original message data"""
    try:
        message_bytes = message.encode("utf-8") + str(counter).encode("utf-8")
        public_key.verify(
            base64.b64decode(signature),
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        print("Invalid signature.")
        return False
