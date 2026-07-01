from __future__ import annotations


def test_image_material_uses_unlimited_ocr_adapter(monkeypatch) -> None:
    from app import ocr_service
    from app.materials import extract_material_text

    monkeypatch.setenv("BLANK_OCR_ENABLED", "true")
    monkeypatch.setattr(
        ocr_service,
        "extract_image_text",
        lambda filename, content_type, raw: f"OCR:{filename}:{content_type}:{len(raw)}",
    )

    raw_png = b"\x89PNG\r\n\x1a\n" + b"image-bytes"

    text = extract_material_text("diagram.png", "image/png", raw_png)

    assert text.startswith("OCR:diagram.png:image/png:")


def test_image_material_requires_ocr_when_not_configured(monkeypatch) -> None:
    from app.materials import MaterialParseError, extract_material_text

    monkeypatch.delenv("BLANK_OCR_ENABLED", raising=False)

    try:
        extract_material_text("diagram.jpg", "image/jpeg", b"\xff\xd8\xffimage-bytes")
    except MaterialParseError as exc:
        assert "OCR" in str(exc)
    else:
        raise AssertionError("图片材料未配置 OCR 时必须给出明确错误")
