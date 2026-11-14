"""Bounded, inline image attachments. Never accept active SVG/HTML or URLs."""
import base64
import binascii
import re

MAX_IMAGE_BYTES = 1_572_864  # 1.5 MiB per side
MAX_IMAGE_DATA_URL_LENGTH = ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 64
_DATA_IMAGE = re.compile(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]*={0,2})\Z")


def validate_card_image(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_IMAGE_DATA_URL_LENGTH:
        raise ValueError("Each card photo must be a PNG, JPEG, or WebP image no larger than 1.5 MiB.")
    match = _DATA_IMAGE.fullmatch(value)
    if match is None:
        raise ValueError("Use an uploaded PNG, JPEG, or WebP image.")
    try:
        content = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("The uploaded image is not valid base64 data.") from exc
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Each card photo must be no larger than 1.5 MiB.")
    mime = match[1]
    valid = False
    if mime == 'png':
        valid = (len(content) >= 45 and content.startswith(b'\x89PNG\r\n\x1a\n') and
                 content[12:16] == b'IHDR' and content[-12:] == b'\x00\x00\x00\x00IEND\xaeB`\x82')
        if valid:
            width = int.from_bytes(content[16:20], 'big')
            height = int.from_bytes(content[20:24], 'big')
            valid = 0 < width <= 8192 and 0 < height <= 8192 and width * height <= 16_777_216
    elif mime == 'jpeg':
        valid = len(content) >= 12 and content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9')
    elif mime == 'webp':
        valid = (len(content) >= 20 and content[:4] == b'RIFF' and content[8:12] == b'WEBP' and
                 content[12:16] in {b'VP8 ', b'VP8L', b'VP8X'} and
                 int.from_bytes(content[4:8], 'little') == len(content) - 8)
    if not valid:
        raise ValueError("The image content does not match its PNG, JPEG, or WebP type.")
    return value
