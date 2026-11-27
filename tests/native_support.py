"""Small, real synthetic PDFs for native-first reading tests (no third-party writer needed)."""

from __future__ import annotations

from pathlib import Path


def _pdf(path: Path, streams: list[bytes]) -> None:
    """Write a valid PDF with one page per content stream (Helvetica available as /F1)."""
    pages = len(streams)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    font_number = 3 + 2 * pages
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()]
    for index, stream in enumerate(streams):
        content = 4 + 2 * index
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content} 0 R "
                       f"/Resources << /Font << /F1 {font_number} 0 R >> >> >>".encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + content + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def text_stream(lines: list[str]) -> bytes:
    text = "BT /F1 11 Tf 40 780 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines
    ) + " ET"
    return text.encode("cp1252")


def drawing_stream() -> bytes:
    """Vector shapes only: a box and an arrow, nothing a text extractor can return."""
    return b"0.2 0.4 0.8 RG 2 w 60 600 180 80 re S 240 640 m 330 640 l S 330 640 m 318 648 l 318 632 l h f"


def text_pdf(path: Path, lines: list[str]) -> None:
    _pdf(path, [text_stream(lines)])


def drawn_pdf(path: Path, pages: int = 1) -> None:
    """A PDF with no text layer at all (as a scan or a drawn diagram would be)."""
    _pdf(path, [drawing_stream() for _ in range(pages)])


def mixed_pdf(path: Path, lines: list[str]) -> None:
    """Page 1 carries text; page 2 carries only a drawing."""
    _pdf(path, [text_stream(lines), drawing_stream()])
