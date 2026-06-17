from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from urllib.parse import unquote

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .security import MAX_UPLOAD_BYTES


MAX_PDF_PAGES = 80
MAX_MATERIAL_CHARS = 20000
MATERIAL_TRUNCATE_BUFFER_CHARS = 1000
MAX_MATERIAL_TITLE_CHARS = 120
TEXT_SAMPLE_BYTES = 4096

TEXT_EXTENSIONS = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".log",
    ".md",
    ".markdown",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_CONTENT_PREFIXES = ("text/",)
TEXT_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
}
UNSUPPORTED_BINARY_SIGNATURES: tuple[bytes, ...] = (
    b"MZ",
    b"\x7fELF",
    b"\xca\xfe\xba\xbe",
    b"\xfe\xed\xfa",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"\x1f\x8b\x08",
    b"BZh",
    b"Rar!\x1a\x07",
    b"7z\xbc\xaf\x27\x1c",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)
BINARY_CONTROL_BYTES = set(range(0, 32)) - {9, 10, 12, 13}


class MaterialParseError(ValueError):
    pass


def safe_material_title(filename: str | None) -> str:
    raw_name = filename or "上传材料"
    for _ in range(2):
        decoded = unquote(raw_name)
        if decoded == raw_name:
            break
        raw_name = decoded
    name = raw_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = re.sub(r"[\x00-\x1f<>:\"|?*]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    if not name:
        name = "上传材料"
    if len(name) > MAX_MATERIAL_TITLE_CHARS:
        suffix = Path(name).suffix
        keep = MAX_MATERIAL_TITLE_CHARS - len(suffix)
        name = f"{name[:max(1, keep)].rstrip(' ._')}{suffix}" if suffix else name[:MAX_MATERIAL_TITLE_CHARS]
    return name


def extract_material_text(filename: str | None, content_type: str | None, raw: bytes) -> str:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise MaterialParseError(f"文件过大，请上传不超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 的材料。")

    name = safe_material_title(filename)
    suffix = Path(name.lower()).suffix
    media_type = (content_type or "").split(";")[0].strip().lower()
    is_pdf = suffix == ".pdf" or media_type == "application/pdf" or raw.lstrip().startswith(b"%PDF")

    if is_pdf:
        return extract_pdf_text(raw)

    if suffix in TEXT_EXTENSIONS or is_text_content_type(media_type):
        ensure_text_like(raw, suffix or media_type or "该文件")
        return decode_text(raw)

    ensure_text_like(raw, suffix or media_type or "该文件")
    try:
        return decode_text(raw)
    except MaterialParseError as exc:
        raise MaterialParseError(f"暂不支持解析 {suffix or media_type or '该类型'} 文件，请先上传 PDF、TXT 或 Markdown。") from exc


def extract_pdf_text(raw: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw))
    except (PdfReadError, OSError, ValueError, TypeError) as exc:
        raise MaterialParseError("PDF 文件无法读取，请确认文件未损坏或未加密。") from exc

    if reader.is_encrypted:
        raise MaterialParseError("暂不支持解析加密 PDF，请先解除密码保护后再上传。")
    try:
        page_count = len(reader.pages)
    except (PdfReadError, OSError, ValueError, TypeError, KeyError) as exc:
        raise MaterialParseError("PDF 结构无法读取，请确认文件未损坏。") from exc
    if page_count > MAX_PDF_PAGES:
        raise MaterialParseError(f"PDF 页数过多，请上传不超过 {MAX_PDF_PAGES} 页的材料。")

    page_text: list[str] = []
    collected_chars = 0
    for index in range(page_count):
        try:
            page = reader.pages[index]
            text = page.extract_text() or ""
        except (PdfReadError, KeyError, TypeError, ValueError, OSError):
            text = ""
        cleaned = normalize_text(text)
        if cleaned:
            remaining = MAX_MATERIAL_CHARS + MATERIAL_TRUNCATE_BUFFER_CHARS - collected_chars
            if remaining <= 0:
                break
            page_text.append(cleaned[:remaining])
            collected_chars += min(len(cleaned), remaining)
            if collected_chars >= MAX_MATERIAL_CHARS:
                break

    content = normalize_text("\n\n".join(page_text))
    if not content:
        raise MaterialParseError("未能从 PDF 中提取到文本。如果这是扫描版 PDF，请先使用 OCR 转成可复制文本。")
    return limit_material_text(content)


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            content = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        normalized = normalize_text(content[: MAX_MATERIAL_CHARS + MATERIAL_TRUNCATE_BUFFER_CHARS])
        if normalized:
            return limit_material_text(normalized)
    raise MaterialParseError("文件文本编码无法识别，请转换为 UTF-8 后再上传。")


def is_text_content_type(media_type: str) -> bool:
    return media_type.startswith(TEXT_CONTENT_PREFIXES) or media_type in TEXT_CONTENT_TYPES


def ensure_text_like(raw: bytes, label: str) -> None:
    if has_unsupported_binary_signature(raw) or not looks_like_text_bytes(raw):
        raise MaterialParseError(f"{label} 看起来不是可解析文本，请上传 PDF、TXT 或 Markdown。")


def has_unsupported_binary_signature(raw: bytes) -> bool:
    sample = raw[:32]
    return any(sample.startswith(signature) for signature in UNSUPPORTED_BINARY_SIGNATURES)


def looks_like_text_bytes(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:TEXT_SAMPLE_BYTES]
    if b"\x00" in sample:
        return False
    control_count = sum(1 for byte in sample if byte in BINARY_CONTROL_BYTES)
    return control_count / max(len(sample), 1) <= 0.02


def normalize_text(content: str) -> str:
    return "\n".join(line.strip() for line in content.replace("\x00", "").splitlines()).strip()


def limit_material_text(content: str) -> str:
    normalized = normalize_text(content)
    if len(normalized) > MAX_MATERIAL_CHARS:
        return normalized[:MAX_MATERIAL_CHARS]
    return normalized
