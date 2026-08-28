"""Branded HTML/plain-text email rendering for MIU Export Hub.

Emails are composed from a small set of blocks so every notification shares the
same layout, spacing and colour palette. Styles are inlined because Gmail and
Outlook strip or partially support ``<style>`` blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Iterable, Sequence, Union

from app.core.shared.config import get_settings

TEAL = "#006161"
TEAL_DARK = "#004a4a"
GREEN = "#00AA6D"
HEADING = "#334257"
BODY = "#5f6b74"
MUTED = "#8b959d"
PAGE_BG = "#eef3f2"
CARD_BG = "#ffffff"
BORDER = "#e3ebe9"
SOFT_BG = "#f6faf9"

FONT_STACK = (
    "'Roboto',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
)

TONE_COLORS = {
    "info": (TEAL, "#effafa"),
    "success": (GREEN, "#eefaf4"),
    "warning": ("#b26a00", "#fff7e8"),
    "danger": ("#b3261e", "#fdeeed"),
}


@dataclass
class Paragraph:
    text: str
    muted: bool = False


@dataclass
class Details:
    """Label/value summary table, e.g. RFQ reference, product, quantity."""

    rows: Sequence[tuple[str, str | None]]
    title: str | None = None


@dataclass
class Bullets:
    items: Sequence[str]
    title: str | None = None


@dataclass
class Callout:
    body: str
    title: str | None = None
    tone: str = "info"


@dataclass
class Button:
    label: str
    url: str


@dataclass
class Divider:
    pass


EmailBlock = Union[Paragraph, Details, Bullets, Callout, Button, Divider]


@dataclass
class EmailContent:
    subject: str
    text: str
    html: str


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/pdf"


@dataclass
class EmailDocument:
    """A generated document plus the flag controlling whether it is attached."""

    attachment: EmailAttachment
    attach: bool = True
    summary: str | None = None
    fields: list[tuple[str, str]] = field(default_factory=list)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _html_paragraph(block: Paragraph) -> str:
    color = MUTED if block.muted else BODY
    size = "13px" if block.muted else "15px"
    text = escape(_clean(block.text)).replace("\n", "<br />")
    return (
        f'<p style="margin:0 0 16px;color:{color};font-size:{size};'
        f'line-height:24px;">{text}</p>'
    )


def _html_details(block: Details) -> str:
    rows = [(label, value) for label, value in block.rows if _clean(value)]
    if not rows:
        return ""
    cells = []
    for index, (label, value) in enumerate(rows):
        border = "" if index == 0 else f"border-top:1px solid {BORDER};"
        cells.append(
            f'<tr>'
            f'<td style="{border}padding:10px 0;color:{MUTED};font-size:12px;'
            f'text-transform:uppercase;letter-spacing:.4px;white-space:nowrap;'
            f'vertical-align:top;">{escape(label)}</td>'
            f'<td style="{border}padding:10px 0 10px 16px;color:{HEADING};'
            f'font-size:14px;font-weight:600;text-align:right;">'
            f'{escape(_clean(value)).replace(chr(10), "<br />")}</td>'
            f'</tr>'
        )
    title = ""
    if block.title:
        title = (
            f'<p style="margin:0 0 6px;color:{HEADING};font-size:13px;'
            f'font-weight:700;text-transform:uppercase;letter-spacing:.5px;">'
            f"{escape(block.title)}</p>"
        )
    return (
        f'{title}<table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" style="width:100%;border-collapse:collapse;'
        f'background:{SOFT_BG};border:1px solid {BORDER};border-radius:10px;'
        f'padding:6px 18px;margin:0 0 22px;">{"".join(cells)}</table>'
    )


def _html_bullets(block: Bullets) -> str:
    items = [escape(_clean(item)) for item in block.items if _clean(item)]
    if not items:
        return ""
    title = ""
    if block.title:
        title = (
            f'<p style="margin:0 0 8px;color:{HEADING};font-size:14px;'
            f'font-weight:600;">{escape(block.title)}</p>'
        )
    lis = "".join(
        f'<li style="margin:0 0 8px;color:{BODY};font-size:14px;'
        f'line-height:22px;">{item}</li>'
        for item in items
    )
    return f'{title}<ul style="margin:0 0 22px;padding-left:20px;">{lis}</ul>'


def _html_callout(block: Callout) -> str:
    accent, background = TONE_COLORS.get(block.tone, TONE_COLORS["info"])
    title = ""
    if block.title:
        title = (
            f'<p style="margin:0 0 6px;color:{accent};font-size:13px;'
            f'font-weight:700;">{escape(block.title)}</p>'
        )
    body = escape(_clean(block.body)).replace("\n", "<br />")
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="width:100%;margin:0 0 22px;"><tr><td style="background:{background};'
        f'border-left:3px solid {accent};border-radius:8px;padding:14px 18px;">'
        f'{title}<p style="margin:0;color:{BODY};font-size:14px;line-height:22px;">'
        f"{body}</p></td></tr></table>"
    )


def _html_button(block: Button) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:4px 0 26px;"><tr><td style="background:{GREEN};'
        f'border-radius:8px;"><a href="{escape(block.url, quote=True)}" '
        f'style="display:inline-block;padding:13px 30px;color:#ffffff;'
        f'font-size:15px;font-weight:600;text-decoration:none;">'
        f"{escape(block.label)}</a></td></tr></table>"
    )


def _html_divider() -> str:
    return f'<hr style="border:none;border-top:1px solid {BORDER};margin:0 0 22px;" />'


def _render_block_html(block: EmailBlock) -> str:
    if isinstance(block, Paragraph):
        return _html_paragraph(block)
    if isinstance(block, Details):
        return _html_details(block)
    if isinstance(block, Bullets):
        return _html_bullets(block)
    if isinstance(block, Callout):
        return _html_callout(block)
    if isinstance(block, Button):
        return _html_button(block)
    return _html_divider()


def _render_block_text(block: EmailBlock) -> str:
    if isinstance(block, Paragraph):
        return _clean(block.text)
    if isinstance(block, Details):
        rows = [(label, value) for label, value in block.rows if _clean(value)]
        if not rows:
            return ""
        lines = []
        if block.title:
            lines.append(block.title.upper())
        width = max(len(label) for label, _ in rows)
        lines.extend(f"{label.ljust(width)}  {_clean(value)}" for label, value in rows)
        return "\n".join(lines)
    if isinstance(block, Bullets):
        items = [_clean(item) for item in block.items if _clean(item)]
        if not items:
            return ""
        lines = [block.title] if block.title else []
        lines.extend(f"  - {item}" for item in items)
        return "\n".join(lines)
    if isinstance(block, Callout):
        prefix = f"{block.title}: " if block.title else ""
        return f"{prefix}{_clean(block.body)}"
    if isinstance(block, Button):
        return f"{block.label}:\n{block.url}"
    return "---"


def render_email(
    *,
    subject: str,
    heading: str,
    greeting: str | None = None,
    preheader: str | None = None,
    blocks: Iterable[EmailBlock] = (),
    eyebrow: str | None = None,
    signoff: str = "The MIU Export Hub Team",
) -> EmailContent:
    """Render a notification into matching HTML and plain-text bodies."""

    settings = get_settings()
    site_url = settings.frontend_base_url.rstrip("/")
    blocks = list(blocks)

    body_html = "".join(_render_block_html(block) for block in blocks)
    greeting_html = ""
    if greeting:
        greeting_html = (
            f'<p style="margin:0 0 14px;color:{HEADING};font-size:16px;'
            f'font-weight:600;">{escape(greeting)}</p>'
        )
    eyebrow_html = ""
    if eyebrow:
        eyebrow_html = (
            f'<p style="margin:0 0 6px;color:{GREEN};font-size:12px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px;">{escape(eyebrow)}</p>'
        )
    preheader_html = ""
    if preheader:
        preheader_html = (
            f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
            f"{escape(preheader)}</div>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT_STACK};">
{preheader_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="550" cellpadding="0" cellspacing="0" style="width:550px;max-width:100%;background:{CARD_BG};border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(15,35,32,.08);">
<tr><td style="background:{TEAL};padding:24px 32px;">
<span style="color:#ffffff;font-size:17px;font-weight:700;letter-spacing:.3px;">Made in Uganda</span>
<span style="color:rgba(255,255,255,.72);font-size:17px;font-weight:400;"> &nbsp;|&nbsp; Export Hub</span>
</td></tr>
<tr><td style="padding:32px;">
{eyebrow_html}
<h1 style="margin:0 0 18px;color:{HEADING};font-size:22px;line-height:30px;font-weight:700;">{escape(heading)}</h1>
{greeting_html}
{body_html}
<p style="margin:26px 0 0;color:{BODY};font-size:14px;line-height:22px;">{escape(signoff)}</p>
</td></tr>
<tr><td style="background:{SOFT_BG};border-top:1px solid {BORDER};padding:20px 32px;">
<p style="margin:0 0 6px;color:{MUTED};font-size:12px;line-height:19px;">
You are receiving this because you have an account on MIU Export Hub.
</p>
<p style="margin:0;color:{MUTED};font-size:12px;line-height:19px;">
<a href="{escape(site_url, quote=True)}" style="color:{TEAL_DARK};text-decoration:none;">{escape(site_url)}</a>
&nbsp;·&nbsp; &copy; Made in Uganda
</p>
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    text_parts: list[str] = []
    if greeting:
        text_parts.append(greeting)
    for block in blocks:
        rendered = _render_block_text(block)
        if rendered:
            text_parts.append(rendered)
    text_parts.append(signoff)
    text_parts.append(f"MIU Export Hub · {site_url}")

    return EmailContent(subject=subject, text="\n\n".join(text_parts) + "\n", html=html)
