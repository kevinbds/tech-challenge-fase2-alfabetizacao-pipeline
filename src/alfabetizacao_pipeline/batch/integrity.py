import base64


def crc32c_base64(payload: bytes) -> str:
    """Return the standard base64-encoded Castagnoli checksum."""
    checksum = 0xFFFFFFFF
    for byte in payload:
        checksum ^= byte
        for _ in range(8):
            checksum = (checksum >> 1) ^ (0x82F63B78 if checksum & 1 else 0)
    encoded = ((checksum ^ 0xFFFFFFFF) & 0xFFFFFFFF).to_bytes(4, byteorder="big")
    return base64.b64encode(encoded).decode("ascii")
