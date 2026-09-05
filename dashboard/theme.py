"""Visual theme shared by the dashboard page and every Plotly figure on it.

Modelled on cognition.ai: warm off-white paper, near-black ink, one electric-blue accent,
serif body copy with a plain grotesque for headings, labels and numbers, and a monospace
for file / column names. The licensed originals (STK Bureau Serif, NB International Pro)
are swapped for open equivalents served from Google Fonts.

Change a value here and rebuild (`python3 build.py dashboard`) to restyle the whole page.
"""

# ---- palette
PAPER = "#f7f6f5"        # page background
SURFACE = "#ffffff"      # cards
INK = "#191919"          # text
MUTE = "#6f6d6a"         # secondary text
LINE = "rgba(0,0,0,.09)"  # hairline borders
ACCENT = "#2200ff"       # links, primary series, highlighted numbers
WARN = "#9f2d00"         # findings that need attention
NEUTRAL = "#d9d5d1"      # de-emphasised bars / dropped-out flows
NEUTRAL_DARK = "#a8a49f"
NAVY = "#17293f"         # logo tile
BATON = "#c4763e"        # logo diagonal; the connector tab row


def logo(size=30):
    """The Halyard mark as inline SVG: navy tile, two white uprights, the orange baton between them."""
    return (f'<svg class="logo" width="{size}" height="{size}" viewBox="0 0 40 40" aria-hidden="true">'
            f'<rect width="40" height="40" rx="7" fill="{NAVY}"/>'
            f'<rect x="9" y="9" width="3.4" height="22" fill="#fff"/>'
            f'<rect x="27.6" y="9" width="3.4" height="22" fill="#fff"/>'
            f'<path d="M12.4 26.4 27.6 14.6" stroke="{BATON}" stroke-width="3"/></svg>')

# ---- type
SERIF = '"Newsreader", "Iowan Old Style", Georgia, serif'
SANS = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
MONO = '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400'
             '&family=Inter:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap">')

# ---- plotly
PLOTLY_LAYOUT = dict(
    font=dict(family=SANS, color=INK, size=12),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE),
    yaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE),
    legend=dict(font=dict(color=MUTE)),
    hoverlabel=dict(font=dict(family=SANS)),
)


def rgba(hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"
