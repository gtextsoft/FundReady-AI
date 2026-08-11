"""Magic-byte upload verification."""

from app.modules.intake.scanning import (
    content_type_matches_bytes,
    head_contains_pe_executable,
)


def test_pdf_magic() -> None:
    assert content_type_matches_bytes("application/pdf", b"%PDF-1.7\n...")


def test_png_magic() -> None:
    assert content_type_matches_bytes("image/png", b"\x89PNG\r\n\x1a\nxxxx")


def test_mismatched_type_is_rejected() -> None:
    assert content_type_matches_bytes("application/pdf", b"MZ\x90\x00") is False


def test_pe_marker_rejected_even_when_pdf_magic_matches() -> None:
    """Polyglot: valid PDF head that also carries an MZ stub → INFECTED."""
    head = b"%PDF-1.7\n....MZ\x90\x00...."
    assert content_type_matches_bytes("application/pdf", head) is True
    assert head_contains_pe_executable(head) is True


def test_csv_rejects_nul() -> None:
    assert content_type_matches_bytes("text/csv", b"a,b,c\n1,2,3") is True
    assert content_type_matches_bytes("text/csv", b"a\x00b") is False
