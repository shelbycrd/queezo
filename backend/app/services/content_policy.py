"""Reject link-like content in deck text; never apply this to credentials/photos."""
import html
import re
import unicodedata
from urllib.parse import unquote

SCHEMES = re.compile(r'\b(?:https?|hxxps?|ftps?|wss?|file|javascript|mailto|tel|ssh|smb|magnet|steam|discord)\s*:', re.I)
GENERIC = re.compile(r'\b[a-z][a-z0-9+.-]*\s*:\s*//|\bdata\s*:[^\s]*[,;]', re.I)
HOST = re.compile(r'(?<![\w@.])(?:www\d*\.|localhost\b|(?:[\w-]+\.)+(?:[^\W\d_]{2,63}|xn--[a-z0-9-]+)(?![\w@])|(?:\d{1,3}\.){3}\d{1,3}\b|\[[0-9a-f]*:[0-9a-f:.]+\])', re.I)


def no_urls(value):
    normalized = unicodedata.normalize('NFKC', value)
    for _ in range(2):
        normalized = unicodedata.normalize('NFKC', html.unescape(unquote(normalized)))
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Cf')
    normalized = re.sub(r'\[\s*\.\s*\]|\(\s*\.\s*\)', '.', normalized).replace('\\', '/')
    if SCHEMES.search(normalized) or GENERIC.search(normalized) or HOST.search(normalized):
        raise ValueError('URL links are not allowed in deck titles, questions, or answers.')
    return value
