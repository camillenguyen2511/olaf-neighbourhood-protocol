import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa, padding, types
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


def generate_fingerprint(self, public_key: types.PublicKeyTypes):
    """Generates a fingerprint based on the public key (hash)."""
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(public_bytes).hexdigest()


def load_pem_public_key(self, public_key_str: str):
    return serialization.load_pem_public_key(
        public_key_str.encode(), backend=default_backend()
    )
