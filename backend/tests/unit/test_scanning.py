"""Magic-byte upload verification."""

from app.modules.intake.scanning import content_type_matches_bytes


def test_pdf_magic() -> None:
    assert content_type_matches_bytes("application/pdf", b"%PDF-1.7\n...")


def test_png_magic() -> None:
    assert content_type_matches_bytes("image/png", b"\x89PNG\r\n\x1a\nxxxx")


def test_mismatched_type_is_rejected() -> None:
    assert content_type_matches_bytes("application/pdf", b"MZ\x90\x00") is False


def test_csv_rejects_nul() -> None:
    assert content_type_matches_bytes("text/csv", b"a,b,c\n1,2,3") is True
    assert content_type_matches_bytes("text/csv", b"a\x00b") is False
