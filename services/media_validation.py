"""Video file content validation by container magic bytes.

Extension checks are trivially spoofable, so after a file is staged we verify
the leading bytes match a known video container signature. This is a
defence-in-depth check; it intentionally errs toward accepting anything that
plausibly matches a real container.
"""

from pathlib import Path


def _looks_like_video_container(head: bytes) -> bool:
    """Return True when the byte prefix matches a known video container."""
    if not head or len(head) < 12:
        return False

    # ISO Base Media (MP4 / MOV / M4V / 3GP / etc.): "....ftyp" at offset 4
    if head[4:8] == b"ftyp":
        return True
    # Matroska / WebM: EBML header
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    # AVI: RIFF....AVI
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return True
    # ASF / WMV: GUID 30 26 B2 75 8E 66 CF 11 ...
    if head[:4] == b"\x30\x26\xb2\x75":
        return True
    # FLV
    if head[:3] == b"FLV":
        return True
    # MPEG transport stream (.ts): sync byte 0x47
    if head[:1] == b"\x47":
        return True
    # MPEG program stream / MPEG-1/2 video: 00 00 01 (B?/BA/start codes)
    if head[:3] == b"\x00\x00\x01":
        return True
    # Ogg (theora/ogv)
    if head[:4] == b"OggS":
        return True
    # EBML/Matroska without strict 4-byte (defensive)
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    return False


def is_valid_video_content(file_path: Path, read_bytes: int = 16) -> bool:
    """Read the file head and check it against known video signatures.

    Returns False on unreadable/empty files or unknown signatures.
    """
    try:
        with open(file_path, "rb") as f:
            head = f.read(max(12, int(read_bytes)))
    except OSError:
        return False
    return _looks_like_video_container(head)
