"""
services/pdf_export_service.py
---------------------------------
Combines a chosen set of a repository's generated Markdown documents into
one formally-formatted PDF (cover page, table of contents, per-document
sections, page numbers) and keeps a flat-file history of past exports —
same on-disk convention as the rest of generated_docs/ (see
document_store_service.py's module docstring), just under a per-repo
exports/ subfolder instead of introducing a database.

Markdown -> HTML -> PDF pipeline: `markdown` (with GFM-ish extensions,
matching the `remark-gfm` flavor the frontend already renders) produces
HTML, which `xhtml2pdf` rasterizes to PDF. xhtml2pdf is pure-Python (no
native GTK/Pango/Cairo toolchain like WeasyPrint needs), so it installs
cleanly on Windows without extra system dependencies.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import markdown as _markdown
from xhtml2pdf import pisa
from xhtml2pdf.config.resources import ResourceAccessPolicy

logger = logging.getLogger(__name__)

_EXPORTS_DIRNAME = "exports"
_HISTORY_FILENAME = "history.json"
_MARKDOWN_EXTENSIONS = [
    "extra",
    "sane_lists",
    "nl2br",
    "toc",
    # superfences (not `extra`'s bundled fenced_code) correctly handles code
    # fences indented inside list items -- see requirements.txt note.
    "pymdownx.superfences",
    "pymdownx.highlight",
]
_MARKDOWN_EXTENSION_CONFIGS = {
    # Plain <pre><code> output, no Pygments span-per-token markup -- keeps
    # the HTML simple and matches the plain code-block styling in _PAGE_CSS
    # rather than needing a Pygments CSS theme too.
    "pymdownx.highlight": {"use_pygments": False},
}

# xhtml2pdf's built-in Courier can't draw box-drawing characters (├──, │,
# └──, →, ...), which show up constantly in ASCII directory trees inside
# README/ARCHITECTURE code blocks -- they'd render as blank boxes. If one of
# these Unicode-complete monospace fonts is present on disk, it's embedded
# via @font-face instead; otherwise this degrades gracefully back to plain
# Courier (still renders, just without those specific glyphs).
_CODE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
]


def _find_code_font() -> Path | None:
    for candidate in _CODE_FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path.resolve()
    return None


# Mermaid diagrams (fenced ```mermaid code blocks -- the frontend already
# renders these live via components/MermaidDiagram.tsx) have no PDF
# equivalent of their own; without this they'd just show up as raw diagram
# syntax in a code block. Rendered locally via the mermaid-cli npm package
# (Node.js + a real Chromium-based browser, both driven through Puppeteer)
# pointed at an already-installed Chrome/Edge so nothing needs its own
# ~300MB Chromium download -- keeps PDF export fully offline, no diagram
# source ever leaves the machine to a third-party rendering service.
_BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]
_MERMAID_FENCE_RE = re.compile(r"^```mermaid\r?\n(.*?)\r?\n```[ \t]*$", re.MULTILINE | re.DOTALL)
_MERMAID_RENDER_TIMEOUT_S = 45


def _find_browser() -> str | None:
    for candidate in _BROWSER_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _render_mermaid_to_data_uri(mermaid_source: str, browser_path: str) -> str | None:
    """Render one Mermaid diagram to a base64 PNG data: URI via mermaid-cli,
    or None on any failure (missing npx, render error, timeout) -- callers
    fall back to leaving the original fenced code block untouched."""
    npx = shutil.which("npx")
    if not npx:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            input_path = tmp / "diagram.mmd"
            output_path = tmp / "diagram.png"
            config_path = tmp / "puppeteer-config.json"
            input_path.write_text(mermaid_source, encoding="utf-8")
            # Forward slashes -- backslashes need doubling to round-trip
            # through JSON and it's not worth the escaping footgun.
            config_path.write_text(
                json.dumps({"executablePath": browser_path.replace("\\", "/")}), encoding="utf-8"
            )

            env = dict(os.environ)
            env["PUPPETEER_SKIP_DOWNLOAD"] = "true"
            result = subprocess.run(
                [
                    "npx", "--yes", "@mermaid-js/mermaid-cli",
                    "-i", str(input_path), "-o", str(output_path),
                    "-p", str(config_path), "-b", "white", "-w", "1400",
                ],
                capture_output=True,
                text=True,
                timeout=_MERMAID_RENDER_TIMEOUT_S,
                env=env,
                shell=True,
            )
            if result.returncode != 0 or not output_path.is_file():
                logger.warning("pdf_export_service: mermaid-cli failed: %s", result.stderr[-500:])
                return None
            encoded = base64.b64encode(output_path.read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    except Exception:
        logger.warning("pdf_export_service: mermaid diagram rendering errored", exc_info=True)
        return None


def _render_mermaid_blocks(markdown_content: str) -> str:
    """Replace every ```mermaid fenced block with an <img> of its rendered
    diagram. No-ops (leaves blocks as plain code) if there's no Mermaid
    content, no local browser found, or a specific diagram fails to render."""
    if not _MERMAID_FENCE_RE.search(markdown_content):
        return markdown_content
    browser = _find_browser()
    if not browser:
        logger.info("pdf_export_service: no local Chrome/Edge found, leaving Mermaid blocks as code")
        return markdown_content

    def replace(match: re.Match[str]) -> str:
        data_uri = _render_mermaid_to_data_uri(match.group(1), browser)
        if data_uri is None:
            return match.group(0)
        # A percentage width silently collapses data: URI images to a
        # zero-size box in this xhtml2pdf version (confirmed empirically --
        # an explicit fixed unit doesn't have the bug and still scales the
        # height proportionally). 16cm comfortably fits the ~17cm content
        # area inside the page's 2cm side margins (see _PAGE_CSS's @page).
        return f'<img src="{data_uri}" style="width:16cm;" />'

    return _MERMAID_FENCE_RE.sub(replace, markdown_content)


class ExportNotFoundError(Exception):
    """Raised when a requested export id has no matching PDF on disk."""


class NoDocumentsSelectedError(Exception):
    """Raised when generate() is called with an empty file selection."""


@dataclass
class ExportRecord:
    id: str
    repository_name: str
    repo_slug: str
    download_filename: str
    title: str
    documents: list[str]
    created_at: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repository_name": self.repository_name,
            "repo_slug": self.repo_slug,
            "download_filename": self.download_filename,
            "title": self.title,
            "documents": self.documents,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
        }


_PAGE_CSS = """
@page {
    size: A4;
    margin: 2.4cm 2cm 2.2cm 2cm;
    @frame footer_frame {
        -pdf-frame-content: footer_content;
        bottom: 0.9cm;
        margin-left: 2cm;
        margin-right: 2cm;
        height: 1cm;
    }
}
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1f2937; line-height: 1.5; }
#footer_content { text-align: center; font-size: 8pt; color: #9ca3af; }

.cover { page-break-after: always; padding-top: 6cm; text-align: center; }
.cover .eyebrow { font-size: 10pt; letter-spacing: 2px; color: #0d9488; font-weight: bold; text-transform: uppercase; }
.cover h1 { font-size: 26pt; color: #111827; margin-top: 0.6cm; margin-bottom: 0.3cm; }
.cover .meta { font-size: 10pt; color: #6b7280; margin-top: 0.4cm; }

.toc h2 { font-size: 14pt; color: #0d9488; border-bottom: 1pt solid #d1d5db; padding-bottom: 6px; }
.toc ol { font-size: 11pt; line-height: 2; }

/* Only .doc-section forces the break between the TOC/cover and each
   document -- .toc used to ALSO carry page-break-after, and stacking two
   break rules on either side of the same boundary produced one genuinely
   blank page between the TOC and the first document. */
.doc-section { page-break-before: always; }
.doc-section h1 { font-size: 18pt; color: #0d9488; border-bottom: 1.5pt solid #0d9488; padding-bottom: 6px; margin-bottom: 0.5cm; }
.doc-section h2 { font-size: 14pt; color: #111827; margin-top: 0.6cm; }
.doc-section h3 { font-size: 12pt; color: #111827; margin-top: 0.5cm; }
.doc-section p { margin: 0.25cm 0; text-align: justify; }
.doc-section ul, .doc-section ol { margin: 0.2cm 0 0.2cm 0.4cm; }
.doc-section li { margin: 0.08cm 0; }
.doc-section a { color: #0d9488; }
/* xhtml2pdf has no support at all for the standard CSS word-break /
   overflow-wrap / table-layout properties (it silently ignores them) --
   -pdf-word-wrap: CJK is its own proprietary equivalent (maps straight to
   ReportLab's character-level wordWrap mode) and is what actually stops a
   long unbroken token (an API route, a file path) from overflowing past
   its cell instead of wrapping. */
.doc-section code { font-family: "CodeFont", Courier, monospace; background-color: #f3f4f6; padding: 1px 3px; font-size: 9pt;
                     -pdf-word-wrap: CJK; }
/* -pdf-word-wrap deliberately NOT set on <pre> -- combined with
   white-space: pre-wrap it crashes ReportLab's paragraph splitter on any
   single very long unbroken line (e.g. a one-line Mermaid diagram
   definition raises platypus.doctemplate.LayoutError: Splitting error). */
.doc-section pre { font-family: "CodeFont", Courier, monospace; background-color: #f3f4f6; padding: 8px; font-size: 8.5pt;
                    border: 0.5pt solid #e5e7eb; white-space: pre-wrap; }
.doc-section pre code { background-color: transparent; padding: 0; }
.doc-section table { width: 100%; margin: 0.3cm 0; }
.doc-section th, .doc-section td { border: 0.5pt solid #d1d5db; padding: 4px 6px; font-size: 8.5pt; text-align: left;
                                    -pdf-word-wrap: CJK; }
.doc-section th { background-color: #f0fdfa; color: #0f766e; }
.doc-section blockquote { border-left: 2pt solid #0d9488; margin: 0.3cm 0; padding: 0.1cm 0.4cm; color: #4b5563; }
.doc-section img { margin: 0.3cm 0; border: 0.5pt solid #e5e7eb; }
"""


def _doc_title(relative_filename: str) -> str:
    """'app/api/webhook.py.md' -> 'app/api/webhook.py'; 'README.md' -> 'README'."""
    return re.sub(r"\.md$", "", relative_filename, flags=re.IGNORECASE)


def _render_document_html(relative_filename: str, markdown_content: str) -> str:
    title = _doc_title(relative_filename)
    markdown_content = _render_mermaid_blocks(markdown_content)
    body_html = _markdown.markdown(
        markdown_content, extensions=_MARKDOWN_EXTENSIONS, extension_configs=_MARKDOWN_EXTENSION_CONFIGS
    )
    return f'<div class="doc-section"><h1>{escape(title)}</h1>{body_html}</div>'


def _render_full_html(repository_name: str, titles: list[str], sections_html: list[str], code_font: Path | None) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    toc_items = "".join(f"<li>{escape(t)}</li>" for t in titles)
    font_face_css = (
        f'@font-face {{ font-family: "CodeFont"; src: url("{code_font.as_uri()}"); }}' if code_font else ""
    )

    return f"""<html>
<head><meta charset="utf-8" /><style>{font_face_css}{_PAGE_CSS}</style></head>
<body>
  <div id="footer_content">Page <pdf:pagenumber /> of <pdf:pagecount /> &mdash; {escape(repository_name)}</div>

  <div class="cover">
    <div class="eyebrow">DocuBear &middot; Generated Documentation</div>
    <h1>{escape(repository_name)}</h1>
    <div class="meta">Exported on {generated_at}</div>
    <div class="meta">{len(titles)} document{"s" if len(titles) != 1 else ""} included</div>
  </div>

  <div class="toc">
    <h2>Contents</h2>
    <ol>{toc_items}</ol>
  </div>

  {"".join(sections_html)}
</body>
</html>"""


class PdfExportService:
    """Generates and tracks history for repository documentation PDF exports."""

    def __init__(self, generated_docs_root: Path) -> None:
        self._root = generated_docs_root.resolve()

    def _repo_slug(self, repository_name: str) -> str:
        return repository_name.replace("/", "_")

    def _repo_docs_dir(self, repo_slug: str) -> Path:
        return (self._root / repo_slug).resolve()

    def _exports_dir(self, repo_slug: str) -> Path:
        path = self._repo_docs_dir(repo_slug) / _EXPORTS_DIRNAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _history_path(self, repo_slug: str) -> Path:
        return self._exports_dir(repo_slug) / _HISTORY_FILENAME

    def _read_history(self, repo_slug: str) -> list[dict[str, Any]]:
        history_path = self._history_path(repo_slug)
        if not history_path.is_file():
            return []
        try:
            return json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("pdf_export_service: unreadable history file %s, treating as empty", history_path)
            return []

    def _write_history(self, repo_slug: str, records: list[dict[str, Any]]) -> None:
        self._history_path(repo_slug).write_text(json.dumps(records, indent=2), encoding="utf-8")

    def generate(self, repository_name: str, filenames: list[str], title: str | None = None) -> ExportRecord:
        """Render the selected documents into one PDF and record it in history.

        Args:
            repository_name: Full repo name, e.g. 'owner/repo'.
            filenames: Paths relative to generated_docs/<repo_slug>/, e.g.
                ['README.md', 'app/api/webhook.py.md'] -- same identifiers
                the GitBook publish flow already uses.
            title: Optional custom title for the cover page; defaults to
                repository_name.

        Raises:
            NoDocumentsSelectedError: if filenames is empty.
            FileNotFoundError: if the repo's docs folder or a selected file
                doesn't exist on disk.
        """
        cleaned = [f.replace("\\", "/").lstrip("/") for f in filenames if f.strip()]
        if not cleaned:
            raise NoDocumentsSelectedError("No documents were selected to export.")

        repo_slug = self._repo_slug(repository_name)
        docs_dir = self._repo_docs_dir(repo_slug)
        if not docs_dir.exists():
            raise FileNotFoundError(f"No generated documentation folder found for '{repository_name}'.")

        titles: list[str] = []
        sections_html: list[str] = []
        included: list[str] = []
        for relative_filename in cleaned:
            doc_path = (docs_dir / relative_filename).resolve()
            if docs_dir not in doc_path.parents or not doc_path.is_file():
                logger.warning("pdf_export_service: skipping missing file %s for %s", relative_filename, repository_name)
                continue
            content = doc_path.read_text(encoding="utf-8")
            titles.append(_doc_title(relative_filename))
            sections_html.append(_render_document_html(relative_filename, content))
            included.append(relative_filename)

        if not included:
            raise FileNotFoundError("None of the selected documents were found on disk.")

        display_title = title.strip() if title and title.strip() else repository_name
        code_font = _find_code_font()
        html = _render_full_html(display_title, titles, sections_html, code_font)

        # xhtml2pdf sandboxes local file reads to the working directory by
        # default; explicitly allow the one extra directory the embedded
        # code font (if any) lives in, without opening up local file access
        # more broadly than that.
        resource_policy = (
            ResourceAccessPolicy(base_dir=Path.cwd(), extra_roots=(code_font.parent,)) if code_font else None
        )

        buffer = BytesIO()
        result = pisa.CreatePDF(html, dest=buffer, resource_policy=resource_policy)
        if result.err:
            raise RuntimeError(f"PDF rendering failed with {result.err} error(s).")
        pdf_bytes = buffer.getvalue()

        created_at = datetime.now(timezone.utc)
        export_id = f"{created_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        pdf_path = self._exports_dir(repo_slug) / f"{export_id}.pdf"
        pdf_path.write_bytes(pdf_bytes)

        download_filename = f"{repo_slug}-docs-{created_at.strftime('%Y%m%d-%H%M%S')}.pdf"
        record = ExportRecord(
            id=export_id,
            repository_name=repository_name,
            repo_slug=repo_slug,
            download_filename=download_filename,
            title=display_title,
            documents=included,
            created_at=created_at.isoformat(),
            size_bytes=len(pdf_bytes),
        )

        history = self._read_history(repo_slug)
        history.insert(0, record.to_dict())
        self._write_history(repo_slug, history)

        return record

    def list_exports(self, repository_name: str) -> list[ExportRecord]:
        repo_slug = self._repo_slug(repository_name)
        return [ExportRecord(**entry) for entry in self._read_history(repo_slug)]

    def resolve_export_path(self, repo_slug: str, export_id: str) -> Path:
        """Resolve an export id to its PDF path, validated against traversal."""
        if "/" in repo_slug or ".." in repo_slug or "/" in export_id or ".." in export_id:
            raise ExportNotFoundError(f"Invalid export reference: {repo_slug}/{export_id}")

        exports_dir = self._exports_dir(repo_slug)
        pdf_path = (exports_dir / f"{export_id}.pdf").resolve()
        if exports_dir not in pdf_path.parents or not pdf_path.is_file():
            raise ExportNotFoundError(f"No export found for id: {export_id!r}")
        return pdf_path

    def download_filename_for(self, repo_slug: str, export_id: str) -> str:
        """Look up the human-readable filename recorded for this export id,
        falling back to the opaque id if the history entry is missing."""
        for entry in self._read_history(repo_slug):
            if entry.get("id") == export_id:
                return entry.get("download_filename") or f"{export_id}.pdf"
        return f"{export_id}.pdf"
