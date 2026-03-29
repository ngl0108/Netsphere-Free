from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _write_file(path: Path, data: bytes, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate RSA key pair for license signing/verification.")
    parser.add_argument("--private-key", default="private_key.pem", help="Output path for private key")
    parser.add_argument("--public-key", default="public_key.pem", help="Output path for public key")
    parser.add_argument("--bits", type=int, default=2048, help="RSA key size (default: 2048)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=max(2048, int(args.bits or 2048)))
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path = Path(args.private_key)
    public_path = Path(args.public_key)
    _write_file(private_path, private_bytes, force=bool(args.force))
    _write_file(public_path, public_bytes, force=bool(args.force))

    print(f"Private key: {private_path}")
    print(f"Public key : {public_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
