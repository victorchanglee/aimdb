"""PDF -> plain text, one .txt per paper, for the agent to read.

pypdf's extraction is imperfect on multi-column layouts and tables; the
CLAUDE.md policy tells the agent to mark garbled papers text_unreadable
rather than guess, so fidelity problems fail safe.
"""
from pypdf import PdfReader

from . import config, index


def extract_text(row):
    """Extract text for an index row; returns (ok, detail)."""
    pdf_path = index.find_pdf(row)
    if pdf_path is None:
        return False, "no PDF on disk for this key (fetch first)"
    dest = config.TEXT_DIR / f"{row['key']}.txt"
    try:
        reader = PdfReader(pdf_path)
        pages = []
        for n, page in enumerate(reader.pages, 1):
            pages.append(f"--- page {n} ---\n{page.extract_text() or ''}")
        text = "\n\n".join(pages)
        if len(text.strip()) < 500:
            raise ValueError(
                f"only {len(text.strip())} chars extracted — likely a "
                "scanned/image PDF")
        dest.write_text(text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        index.set_status(row["key"], "text_unreadable")
        index.log_extraction(row["key"], row["doi"], "text",
                             "text_unreadable",
                             f"{type(exc).__name__}: {exc}")
        return False, str(exc)
    index.set_status(row["key"], "text_ready", text_path=config.rel_path(dest))
    index.log_extraction(row["key"], row["doi"], "text", "text_ready",
                         f"{len(reader.pages)} pages -> {dest.name}")
    return True, str(dest)
