"""Small, safe Markdown renderer for the project-owned Web guide."""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urlparse

from markupsafe import Markup


HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
STRONG_RE = re.compile(r"\*\*([^*]+)\*\*")


def _safe_link(url: str) -> str | None:
    value = url.strip()
    parsed = urlparse(value)
    if value.startswith("#") or parsed.scheme in {"http", "https"}:
        return value
    return None


def _inline(value: str) -> str:
    escaped = html.escape(value, quote=True)
    code_tokens: list[str] = []

    def keep_code(match: re.Match[str]) -> str:
        code_tokens.append(f"<code>{match.group(1)}</code>")
        return f"\x00CODE{len(code_tokens) - 1}\x00"

    escaped = CODE_RE.sub(keep_code, escaped)
    escaped = STRONG_RE.sub(r"<strong>\1</strong>", escaped)

    def link(match: re.Match[str]) -> str:
        target = html.unescape(match.group(2))
        safe_target = _safe_link(target)
        if safe_target is None:
            return match.group(1)
        external = urlparse(safe_target).scheme in {"http", "https"}
        attributes = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return f'<a href="{html.escape(safe_target, quote=True)}"{attributes}>{match.group(1)}</a>'

    escaped = LINK_RE.sub(link, escaped)
    for index, token in enumerate(code_tokens):
        escaped = escaped.replace(f"\x00CODE{index}\x00", token)
    return escaped


def _slug(text: str, used: set[str]) -> str:
    base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-").lower()
    base = base or "section"
    slug = base
    suffix = 2
    while slug in used:
        slug = f"{base}-{suffix}"
        suffix += 1
    used.add(slug)
    return slug


def render_markdown(markdown: str) -> Markup:
    """Render the guide's supported Markdown subset with escaped raw HTML."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    used_slugs: set[str] = set()

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                language = re.sub(r"[^a-zA-Z0-9_-]", "", code_language)
                class_name = f' class="language-{language}"' if language else ""
                output.append(
                    f"<pre><code{class_name}>{html.escape(chr(10).join(code_lines))}</code></pre>"
                )
                in_code = False
                code_lines.clear()
                code_language = ""
            else:
                code_lines.append(line)
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            in_code = True
            code_language = stripped[3:].strip()
            index += 1
            continue

        heading = HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            text = heading.group(2)
            output.append(
                f'<h{level} id="{_slug(text, used_slugs)}">{_inline(text)}</h{level}>'
            )
            index += 1
            continue

        if stripped == "---":
            flush_paragraph()
            close_list()
            output.append("<hr>")
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines):
            separator = lines[index + 1].strip()
            if separator.startswith("|") and re.fullmatch(r"[|:\- ]+", separator):
                flush_paragraph()
                close_list()
                headers = [cell.strip() for cell in stripped.strip("|").split("|")]
                output.append("<div class=\"guide-table-wrap\"><table><thead><tr>")
                output.extend(f"<th>{_inline(cell)}</th>" for cell in headers)
                output.append("</tr></thead><tbody>")
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                    output.append("<tr>")
                    output.extend(f"<td>{_inline(cell)}</td>" for cell in cells)
                    output.append("</tr>")
                    index += 1
                output.append("</tbody></table></div>")
                continue

        unordered = stripped.startswith("- ")
        ordered = ORDERED_RE.match(stripped)
        if unordered or ordered:
            flush_paragraph()
            next_type = "ul" if unordered else "ol"
            if list_type != next_type:
                close_list()
                list_type = next_type
                output.append(f"<{list_type}>")
            item = stripped[2:] if unordered else ordered.group(1)
            output.append(f"<li>{_inline(item)}</li>")
            index += 1
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            close_list()
        else:
            if list_type:
                close_list()
            paragraph.append(stripped)
        index += 1

    if in_code:
        output.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    close_list()
    return Markup("\n".join(output))


def render_markdown_file(path: Path) -> Markup:
    return render_markdown(path.read_text(encoding="utf-8"))
