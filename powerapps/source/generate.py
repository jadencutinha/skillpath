"""Generate the Training Portal canvas app source.

    python powerapps/source/generate.py

Writes, next to this file:
    App.Formulas.fx          named formulas to paste into App.Formulas
    scrHome.pa.yaml          one file per screen, in Power Apps YAML (paste with "Paste code")
    scrCatalog.pa.yaml
    scrNewRequest.pa.yaml
    scrApprovals.pa.yaml
    preview.html             a static mock of the four screens with sample data

The screens are described once, as a tree of controls, and emitted twice: as Power Apps
YAML and as HTML. The HTML is only a design check (it shows layout, colour and type, with
sample data in place of formulas); the YAML is the product.

Every control sets its style properties explicitly. A pasted control that omits a property
takes the app theme's default, which is how a design ends up with stray blue buttons.

Layout is fixed at the Tablet canvas, 1366 x 768. Leave the app's "Scale to fit" setting on.
Nothing depends on z-order: sibling controls never overlap, so the order Studio assigns
when pasting cannot hide one behind another.
"""

from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).parent
W, H = 1366, 768
NAV = 232
PAD = 28
X0 = NAV + PAD  # left edge of the content area
CW = W - NAV - 2 * PAD  # content width (1078)

# ───────────────────────── theme ─────────────────────────

HEX = {
    "Navy": "#0B1F3A",
    "NavyLift": "#16305A",
    "NavText": "#B9C6DB",
    "Canvas": "#F4F6FA",
    "Surface": "#FFFFFF",
    "SurfaceAlt": "#F8FAFC",
    "Border": "#E3E8EF",
    "Ink": "#0F1B2D",
    "Body": "#344054",
    "Muted": "#5B6B82",
    "Subtle": "#8A97AB",
    "Primary": "#2457D6",
    "PrimaryHover": "#1D48B5",
    "PrimaryPressed": "#173A93",
    "PrimaryTint": "#EAF0FE",
    "Danger": "#B42318",
    "DangerTint": "#FDECEA",
    "Warn": "#B54708",
    "WarnTint": "#FEF0E1",
    "Good": "#15803D",
    "GoodTint": "#E7F6EC",
    "White": "#FFFFFF",
    "Disabled": "#D5DBE5",
}

# Key, foreground, background, rank on the progress tracker, ended-badly flag
STATUS_STYLES = [
    ("Draft", "#475467", "#EEF1F5", 1, False),
    ("Submitted", "#1D4ED8", "#DCE7FD", 2, False),
    ("Approved", "#15803D", "#E7F6EC", 3, False),
    ("Completed", "#0F766E", "#E0F5F2", 4, False),
    ("Rejected", "#B42318", "#FDECEA", 3, True),
    ("Expired", "#B54708", "#FEF0E1", 3, True),
    ("Withdrawn", "#475467", "#EEF1F5", 3, True),
    ("Error", "#912018", "#FDECEA", 3, True),
]
STATUS = {k: (fg, bg, rank, bad) for k, fg, bg, rank, bad in STATUS_STYLES}

CATEGORY_HEX = {
    "Technical": ("#1D4ED8", "#E8EFFE"),
    "Leadership": ("#7A3EB1", "#F3EAFB"),
    "Compliance": ("#0F766E", "#E0F5F2"),
    "Professional Development": ("#B54708", "#FEF0E1"),
}

# 24x24 stroke icons. Drawn inline as SVG so the app needs no image uploads.
ICONS = {
    "Home": "<path d='M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z'/>",
    "Catalog": "<path d='M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2z'/><path d='M22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z'/>",
    "Approvals": "<circle cx='12' cy='12' r='9'/><path d='m8.5 12.5 2.5 2.5 4.5-5'/>",
    "Plus": "<path d='M12 5v14M5 12h14'/>",
    "Search": "<circle cx='11' cy='11' r='7'/><path d='m20 20-3.5-3.5'/>",
    "Refresh": "<path d='M20 11a8 8 0 1 0-2.3 5.7'/><path d='M20 4v7h-7'/>",
    "Back": "<path d='M19 12H5M11 6l-6 6 6 6'/>",
    "User": "<circle cx='12' cy='8' r='4'/><path d='M4 21a8 8 0 0 1 16 0'/>",
    "Cap": "<path d='M2 9l10-5 10 5-10 5z'/><path d='M6 11.5V16c2 2 10 2 12 0v-4.5'/><path d='M22 9v6'/>",
}

FONT = "Font.'Segoe UI'"


def tok(name: str) -> tuple[str, str]:
    """A theme colour as (Power Fx formula, hex for the preview)."""
    return f"fxTheme.{name}", HEX[name]


def col(c) -> tuple[str, str]:
    """Accept a theme token name or an explicit (formula, preview hex) pair."""
    return tok(c) if isinstance(c, str) else c


TRANSPARENT = ("RGBA(0, 0, 0, 0)", "transparent")

# ───────────────────────── control helpers ─────────────────────────


def q(text: str) -> str:
    """A Power Fx string literal."""
    return '"' + text.replace('"', '""') + '"'


def node(name, control, props, *, variant=None, children=None, pv=None):
    return {
        "name": name,
        "control": control,
        "variant": variant,
        "props": props,
        "children": children or [],
        "pv": pv or {},
    }


def geom(x, y, w, h) -> tuple[dict, dict]:
    """Split geometry into formula props and preview numbers. A value may be a number or (formula, number)."""
    props, pv = {}, {}
    for key, short, value in (("X", "x", x), ("Y", "y", y), ("Width", "w", w), ("Height", "h", h)):
        if value is None:
            continue
        formula, number = value if isinstance(value, tuple) else (str(value), value)
        props[key] = formula
        pv[short] = number
    return props, pv


def label(
    name,
    text,
    x,
    y,
    w,
    h,
    *,
    size=11,
    color="Body",
    weight=None,
    align=None,
    valign="Middle",
    wrap=False,
    fill=None,
    pad=0,
    demo=None,
    on_select=None,
    visible=None,
    hover_color=None,
    show=True,
):
    cf, ch = col(color)
    props, pv = geom(x, y, w, h)
    props |= {
        "Text": text,
        "Font": FONT,
        "Size": str(size),
        "Color": cf,
        "FontWeight": f"FontWeight.{weight or 'Normal'}",
        "VerticalAlign": f"VerticalAlign.{valign}",
        "Wrap": "true" if wrap else "false",
        "PaddingLeft": str(pad),
        "PaddingRight": str(pad),
        "PaddingTop": "0",
        "PaddingBottom": "0",
        "BorderThickness": "0",
        "FocusedBorderThickness": "0",
    }
    if align:
        props["Align"] = f"Align.{align}"
    if fill:
        props["Fill"] = col(fill)[0]
    if on_select:
        props["OnSelect"] = on_select
    if hover_color:
        props["HoverColor"] = col(hover_color)[0]
    if visible:
        props["Visible"] = visible
    pv |= {
        "kind": "label",
        "text": demo if demo is not None else _literal(text),
        "size": size,
        "color": ch,
        "weight": weight,
        "align": align,
        "valign": valign,
        "wrap": wrap,
        "fill": col(fill)[1] if fill else None,
        "pad": pad,
        "show": show,
    }
    return node(name, "Label", props, pv=pv)


BUTTON_KINDS = {
    #            fill        text       hover fill      pressed fill      border
    "primary": ("Primary", "White", "PrimaryHover", "PrimaryPressed", None),
    "secondary": ("Surface", "Ink", "SurfaceAlt", "Border", "Border"),
    "ghost": ("Canvas", "Muted", "Border", "Border", None),
    "danger": ("Surface", "Danger", "DangerTint", "DangerTint", "Border"),
}


def button(
    name, text, x, y, w, h, *, kind="primary", on_select, size=10.5, visible=None, display=None, demo=None, show=True
):
    fill, color, hover, pressed, border = BUTTON_KINDS[kind]
    props, pv = geom(x, y, w, h)
    props |= {
        "Text": text,
        "OnSelect": on_select,
        "Font": FONT,
        "Size": str(size),
        "FontWeight": "FontWeight.Semibold",
        "Fill": tok(fill)[0],
        "Color": tok(color)[0],
        "HoverFill": tok(hover)[0],
        "HoverColor": tok(color)[0],
        "PressedFill": tok(pressed)[0],
        "PressedColor": tok(color)[0],
        "DisabledFill": tok("Disabled")[0],
        "DisabledColor": tok("White")[0],
        "BorderThickness": "1" if border else "0",
        "BorderColor": tok(border)[0] if border else TRANSPARENT[0],
        "HoverBorderColor": tok(border)[0] if border else TRANSPARENT[0],
        "PressedBorderColor": tok(border)[0] if border else TRANSPARENT[0],
        "DisabledBorderColor": TRANSPARENT[0],
        "FocusedBorderThickness": "2",
        "FocusedBorderColor": tok("Primary")[0],
        "RadiusTopLeft": "8",
        "RadiusTopRight": "8",
        "RadiusBottomLeft": "8",
        "RadiusBottomRight": "8",
        "PaddingLeft": "8",
        "PaddingRight": "8",
        "PaddingTop": "0",
        "PaddingBottom": "0",
    }
    if visible:
        props["Visible"] = visible
    if display:
        props["DisplayMode"] = display
    pv |= {
        "kind": "button",
        "text": demo if demo is not None else _literal(text),
        "size": size,
        "fill": HEX[fill],
        "color": HEX[color],
        "border": HEX[border] if border else None,
        "radius": 8,
        "show": show,
    }
    return node(name, "Classic/Button", props, pv=pv)


def pill(name, text, x, y, w, h, *, fg, bg, size=9, demo=None, demo_fg=None, demo_bg=None, visible=None, show=True):
    """A rounded status tag. A view-mode button, because labels have no corner radius."""
    (ff, fh), (bf, bh) = col(fg), col(bg)
    radius = str(h // 2)
    props, pv = geom(x, y, w, h)
    props |= {
        "Text": text,
        "OnSelect": "false",
        "DisplayMode": "DisplayMode.View",
        "Font": FONT,
        "Size": str(size),
        "FontWeight": "FontWeight.Semibold",
        "Fill": bf,
        "Color": ff,
        "HoverFill": bf,
        "HoverColor": ff,
        "PressedFill": bf,
        "PressedColor": ff,
        "DisabledFill": bf,
        "DisabledColor": ff,
        "BorderThickness": "0",
        "FocusedBorderThickness": "0",
        "RadiusTopLeft": radius,
        "RadiusTopRight": radius,
        "RadiusBottomLeft": radius,
        "RadiusBottomRight": radius,
        "PaddingLeft": "4",
        "PaddingRight": "4",
        "PaddingTop": "0",
        "PaddingBottom": "0",
    }
    if visible:
        props["Visible"] = visible
    pv |= {
        "kind": "button",
        "text": demo if demo is not None else _literal(text),
        "size": size,
        "fill": demo_bg or bh,
        "color": demo_fg or fh,
        "border": None,
        "radius": h // 2,
        "show": show,
    }
    return node(name, "Classic/Button", props, pv=pv)


def rect(name, x, y, w, h, *, fill="Border", visible=None, demo_fill=None, show=True):
    ff, fh = col(fill)
    props, pv = geom(x, y, w, h)
    props |= {"Fill": ff, "BorderThickness": "0", "FocusedBorderThickness": "0", "HoverFill": ff, "PressedFill": ff}
    if visible:
        props["Visible"] = visible
    pv |= {"kind": "rect", "fill": demo_fill or fh, "show": show}
    return node(name, "Rectangle", props, pv=pv)


def icon(name, key, x, y, size, *, stroke="Muted", on_select=None, visible=None, tooltip=None):
    """An inline SVG icon. `stroke` is a key of fxHex / HEX."""
    props, pv = geom(x, y, size, size)
    props |= {
        "Image": (
            '"data:image/svg+xml;utf8," & EncodeUrl('
            "\"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='\" & "
            f"fxHex.{stroke} & "
            "\"' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>\" & "
            f'fxIcon.{key} & "</svg>")'
        ),
        "ImagePosition": "ImagePosition.Fit",
        "BorderThickness": "0",
        "FocusedBorderThickness": "0",
    }
    if on_select:
        props["OnSelect"] = on_select
    if visible:
        props["Visible"] = visible
    if tooltip:
        props["Tooltip"] = q(tooltip)
        props["AccessibleLabel"] = q(tooltip)
    pv |= {"kind": "icon", "icon": key, "stroke": HEX[stroke]}
    return node(name, "Image", props, pv=pv)


def container(
    name, x, y, w, h, children, *, fill="Surface", border="Border", radius=12, shadow=False, visible=None, show=True
):
    ff, fh = col(fill)
    props, pv = geom(x, y, w, h)
    props |= {
        "Fill": ff,
        "BorderThickness": "1" if border else "0",
        "BorderColor": col(border)[0] if border else TRANSPARENT[0],
        "DropShadow": "DropShadow.Light" if shadow else "DropShadow.None",
        "RadiusTopLeft": str(radius),
        "RadiusTopRight": str(radius),
        "RadiusBottomLeft": str(radius),
        "RadiusBottomRight": str(radius),
    }
    if visible:
        props["Visible"] = visible
    pv |= {
        "kind": "container",
        "fill": fh,
        "border": col(border)[1] if border else None,
        "radius": radius,
        "shadow": shadow,
        "show": show,
    }
    return node(name, "GroupContainer", props, variant="ManualLayout", children=children, pv=pv)


def text_input(name, default, x, y, w, h, *, hint, multiline=False, borderless=False, on_change=None, max_length=None):
    props, pv = geom(x, y, w, h)
    radius = "0" if borderless else "8"
    props |= {
        "Default": default,
        "HintText": q(hint),
        "Mode": "TextMode.MultiLine" if multiline else "TextMode.SingleLine",
        "Font": FONT,
        "Size": "11",
        "Color": tok("Ink")[0],
        "Fill": tok("Surface")[0],
        "HoverFill": tok("Surface")[0],
        "BorderThickness": "0" if borderless else "1",
        "BorderColor": tok("Border")[0],
        "HoverBorderColor": tok("Subtle")[0],
        "FocusedBorderThickness": "0" if borderless else "2",
        "FocusedBorderColor": tok("Primary")[0],
        "RadiusTopLeft": radius,
        "RadiusTopRight": radius,
        "RadiusBottomLeft": radius,
        "RadiusBottomRight": radius,
        "PaddingLeft": "4" if borderless else "12",
        "PaddingRight": "12",
        "PaddingTop": "10" if multiline else "0",
        "PaddingBottom": "10" if multiline else "0",
    }
    if on_change:
        props["OnChange"] = on_change
    if max_length:
        props["MaxLength"] = str(max_length)
    pv |= {"kind": "input", "hint": hint, "borderless": borderless, "multiline": multiline}
    return node(name, "Classic/TextInput", props, pv=pv)


def gallery(name, variant, items, x, y, w, h, children, *, template_size, wrap=1, rows=(), template_fill=None, pad=0):
    props, pv = geom(x, y, w, h)
    props |= {
        "Items": items,
        "TemplateSize": str(template_size),
        "TemplatePadding": str(pad),
        "BorderThickness": "0",
        "ShowScrollbar": "true" if variant == "Vertical" else "false",
        "DelayItemLoading": "true",
        "LoadingSpinner": "LoadingSpinner.Data",
    }
    if wrap > 1:
        props["WrapCount"] = str(wrap)
    if template_fill:
        props["TemplateFill"] = template_fill[0]
    pv |= {
        "kind": "gallery",
        "variant": variant,
        "template": template_size,
        "wrap": wrap,
        "rows": list(rows),
        "template_fill": template_fill[1] if template_fill else None,
    }
    return node(name, "Gallery", props, variant=variant, children=children, pv=pv)


def timer(name, *, start, repeat, duration, on_end):
    props = {
        "Start": start,
        "Repeat": repeat,
        "AutoStart": "false",
        "Duration": str(duration),
        "OnTimerEnd": on_end,
        "Visible": "false",
        "X": "0",
        "Y": "0",
    }
    return node(name, "Timer", props, pv={"kind": "hidden"})


def hidden_button(name, on_select):
    """Holds a behaviour formula that several controls trigger with Select()."""
    props = {"OnSelect": on_select, "Visible": "false", "X": "0", "Y": "0", "Width": "10", "Height": "10"}
    return node(name, "Classic/Button", props, pv={"kind": "hidden"})


def _literal(formula: str) -> str:
    """Preview text for a formula that is just a string literal; otherwise show nothing."""
    if formula.startswith('"') and formula.endswith('"') and formula.count('"') == 2:
        return formula[1:-1]
    return ""


def money(expr: str) -> str:
    return f'Text({expr}, "$#,##0")'


def st(key: str) -> str:
    return f"fxStatus.{key}"


def status_style(item: str, field: str) -> str:
    """Look up a colour for a request's status in fxStatusStyles."""
    return f"LookUp(fxStatusStyles, Key = Text({item}.'Request Status')).{field}"


def status_text(item: str) -> str:
    """The status label, replaced by a progress word while a command is waiting for its flow."""
    return (
        "Switch(\n"
        f"    {item}.'Requested Action',\n"
        '    fxAction.Submit, "Submitting…",\n'
        '    fxAction.Withdraw, "Withdrawing…",\n'
        '    fxAction.Complete, "Updating…",\n'
        f"    Text({item}.'Request Status')\n"
        ")"
    )


# ───────────────────────── shared chrome ─────────────────────────

NAV_ITEMS = [
    ("Home", "My requests", "scrHome", None),
    ("Catalog", "Course catalog", "scrCatalog", None),
    ("Approvals", "Approvals", "scrApprovals", "fxIsManager"),
]


def sidebar(suffix: str, active: str) -> dict:
    """The left navigation. Canvas apps can't share one instance across screens, so each screen gets a copy."""
    kids = [
        container(
            f"conLogo{suffix}",
            20,
            22,
            36,
            36,
            [icon(f"imgLogo{suffix}", "Cap", 7, 7, 22, stroke="White")],
            fill="Primary",
            border=None,
            radius=10,
        ),
        label(f"lblApp{suffix}", q("Training Portal"), 68, 20, 150, 22, size=12, color="White", weight="Semibold"),
        label(f"lblAppSub{suffix}", q("Requests & approvals"), 68, 42, 150, 18, size=8.5, color="NavText"),
    ]
    for i, (key, text, screen, visible) in enumerate(NAV_ITEMS):
        is_active = key == active
        go = f"Navigate({screen}, ScreenTransition.Fade)"
        row = [
            icon(f"imgNav{key}{suffix}", key, 12, 9, 22, stroke="White" if is_active else "NavText", on_select=go),
            label(
                f"lblNav{key}{suffix}",
                q(text),
                46,
                0,
                118,
                40,
                size=10.5,
                color="White" if is_active else "NavText",
                weight="Semibold" if is_active else None,
                on_select=go,
                hover_color="White",
            ),
        ]
        if key == "Approvals":
            row.append(
                pill(
                    f"pilNavCount{suffix}",
                    "Text(fxPendingCount)",
                    168,
                    9,
                    28,
                    22,
                    fg="White",
                    bg="Primary",
                    visible="fxPendingCount > 0",
                    demo="3",
                )
            )
        kids.append(
            container(
                f"conNav{key}{suffix}",
                12,
                96 + i * 46,
                208,
                40,
                row,
                fill="NavyLift" if is_active else "Navy",
                border=None,
                radius=8,
                visible=visible,
            )
        )
    kids += [
        rect(f"recNavDivider{suffix}", 20, 694, 192, 1, fill="NavyLift"),
        pill(f"pilUser{suffix}", "fxInitials", 20, 712, 36, 36, fg="White", bg="NavyLift", size=10, demo="JC"),
        label(
            f"lblUser{suffix}",
            "User().FullName",
            66,
            711,
            150,
            20,
            size=10,
            color="White",
            weight="Semibold",
            demo="Jaden Cutinha",
        ),
        label(
            f"lblUserRole{suffix}",
            'If(fxIsManager, "Approver", "Employee")',
            66,
            731,
            150,
            16,
            size=8.5,
            color="NavText",
            demo="Approver",
        ),
    ]
    return container(f"conSidebar{suffix}", 0, 0, NAV, H, kids, fill="Navy", border=None, radius=0)


def page_header(suffix: str, title: str, subtitle: str, *, title_demo=None) -> list[dict]:
    return [
        label(
            f"lblTitle{suffix}",
            title,
            X0,
            24,
            640,
            36,
            size=20,
            color="Ink",
            weight="Semibold",
            demo=title_demo,
        ),
        label(f"lblSubtitle{suffix}", subtitle, X0, 60, 760, 22, size=10.5, color="Muted"),
    ]


def caption(name, text, x, y, w, **kw):
    """Small uppercase field caption."""
    return label(name, q(text.upper()), x, y, w, 16, size=8, color="Subtle", weight="Semibold", **kw)


# ───────────────────────── screen: Home ─────────────────────────

DEMO_REQUESTS = [
    {
        "title": "AWS bootcamp - platform team",
        "sub": "AWS Solutions Architect Associate Bootcamp  ·  $1,450",
        "status": "Submitted",
        "date": "Sep 8",
    },
    {
        "title": "PL-400 for citizen dev lead",
        "sub": "Power Platform Developer (PL-400) Prep  ·  $1,200",
        "status": "Approved",
        "date": "Jun 23",
    },
    {
        "title": "AZ-900 for new cloud team",
        "sub": "Azure Fundamentals (AZ-900)  ·  $165",
        "status": "Completed",
        "date": "Jan 6",
    },
    {
        "title": "Exec leadership cohort",
        "sub": "Executive Leadership Program  ·  $2,495",
        "status": "Rejected",
        "date": "Feb 9",
    },
    {
        "title": "Presentation skills - support lead",
        "sub": "Business Writing and Presentation Skills  ·  $695",
        "status": "Expired",
        "date": "Aug 11",
    },
    {"title": "PMP prep - draft", "sub": "PMP Certification Prep  ·  $1,895", "status": "Draft", "date": ""},
]

SEL = "galMyRequests.Selected"
SEL_STYLE = f"LookUp(fxStatusStyles, Key = Text({SEL}.'Request Status'))"
NO_COMMAND = f"IsBlank({SEL}.'Requested Action')"


def home_filter_items() -> str:
    def any_of(*keys):
        return " || ".join(f"'Request Status' = {st(k)}" for k in keys)

    return (
        "Sort(\n"
        "    Filter(\n"
        "        'Training Requests',\n"
        "        Owner = fxMe,\n"
        '        varHomeFilter = "All"\n'
        f'            || (varHomeFilter = "Active" && ({any_of("Draft", "Submitted")}))\n'
        f'            || (varHomeFilter = "Approved" && ({any_of("Approved", "Completed")}))\n'
        f'            || (varHomeFilter = "Closed" && ({any_of("Rejected", "Withdrawn", "Expired", "Error")}))\n'
        "    ),\n"
        "    'Created On',\n"
        "    SortOrder.Descending\n"
        ")"
    )


def send_command(item: str, action: str, done: str, verb: str) -> str:
    return (
        "IfError(\n"
        f"    Patch('Training Requests', {item}, {{ 'Requested Action': fxAction.{action} }});\n"
        "    Set(varPollTicks, 0);\n"
        "    Set(varPolling, true);\n"
        f"    Notify({q(done)}, NotificationType.Success),\n"
        f'    Notify("Could not {verb}: " & FirstError.Message, NotificationType.Error)\n'
        ")"
    )


def screen_home() -> dict:
    kpi_w = 257
    kpis = [
        ("InReview", "In review", "Text(fxKpiInReview)", "4", "Waiting on an approver"),
        ("Approved", "Approved", "Text(fxKpiApproved)", "17", "Including completed"),
        ("Drafts", "Drafts", "Text(fxKpiDrafts)", "2", "Not submitted yet"),
        ("Spend", "Approved spend", money("fxKpiSpend"), "$14,804", "At the price when requested"),
    ]
    kpi_cards = []
    for i, (key, cap, value, demo, hint) in enumerate(kpis):
        kpi_cards.append(
            container(
                f"conKpi{key}",
                X0 + i * (kpi_w + 16),
                100,
                kpi_w,
                88,
                [
                    caption(f"lblKpiCap{key}", cap, 18, 14, kpi_w - 36),
                    label(
                        f"lblKpiVal{key}",
                        value,
                        18,
                        32,
                        kpi_w - 36,
                        30,
                        size=18,
                        color="Ink",
                        weight="Semibold",
                        demo=demo,
                    ),
                    label(f"lblKpiHint{key}", q(hint), 18, 62, kpi_w - 36, 16, size=8.5, color="Subtle"),
                ],
                shadow=True,
            )
        )

    filters = gallery(
        "galHomeFilter",
        "Horizontal",
        '["All", "Active", "Approved", "Closed"]',
        X0,
        206,
        420,
        34,
        [
            button(
                "btnHomeFilter",
                "ThisItem.Value",
                0,
                0,
                92,
                32,
                kind="secondary",
                on_select="Set(varHomeFilter, ThisItem.Value)",
                size=9.5,
                demo=lambda r: r["label"],
            )
        ],
        template_size=100,
        rows=[{"label": x, "on": x == "All"} for x in ("All", "Active", "Approved", "Closed")],
    )
    chip = filters["children"][0]
    chip["props"] |= {
        "Fill": "If(ThisItem.Value = varHomeFilter, fxTheme.Ink, fxTheme.Surface)",
        "Color": "If(ThisItem.Value = varHomeFilter, fxTheme.White, fxTheme.Body)",
        "HoverColor": "If(ThisItem.Value = varHomeFilter, fxTheme.White, fxTheme.Ink)",
        "HoverFill": "If(ThisItem.Value = varHomeFilter, fxTheme.Ink, fxTheme.SurfaceAlt)",
        "RadiusTopLeft": "16",
        "RadiusTopRight": "16",
        "RadiusBottomLeft": "16",
        "RadiusBottomRight": "16",
    }
    chip["pv"] |= {
        "radius": 16,
        "fill": lambda r: HEX["Ink"] if r["on"] else HEX["Surface"],
        "color": lambda r: HEX["White"] if r["on"] else HEX["Body"],
    }

    list_w, list_h = 680, 494
    rows = gallery(
        "galMyRequests",
        "Vertical",
        home_filter_items(),
        1,
        1,
        list_w - 2,
        list_h - 2,
        [
            rect(
                "recRowBar",
                0,
                0,
                4,
                75,
                fill=(status_style("ThisItem", "Fg"), "#000"),
                demo_fill=lambda r: STATUS[r["status"]][0],
            ),
            label(
                "lblRowTitle",
                "ThisItem.Title",
                22,
                14,
                470,
                24,
                size=11.5,
                color="Ink",
                weight="Semibold",
                on_select="Select(Parent)",
                demo=lambda r: r["title"],
            ),
            label(
                "lblRowSub",
                'ThisItem.Course.Name & "  ·  " & If(IsBlank(ThisItem.\'Course Cost\'), "cost set on submit", '
                + money("ThisItem.'Course Cost'")
                + ")",
                22,
                40,
                470,
                20,
                size=9.5,
                color="Muted",
                on_select="Select(Parent)",
                demo=lambda r: r["sub"],
            ),
            pill(
                "pilRowStatus",
                status_text("ThisItem"),
                ("Parent.TemplateWidth - 136", list_w - 2 - 136),
                13,
                116,
                24,
                fg=(
                    "If(IsBlank(ThisItem.'Requested Action'), " + status_style("ThisItem", "Fg") + ", fxTheme.Muted)",
                    "#000",
                ),
                bg=(
                    "If(IsBlank(ThisItem.'Requested Action'), " + status_style("ThisItem", "Bg") + ", fxTheme.Canvas)",
                    "#fff",
                ),
                demo=lambda r: r["status"],
                demo_fg=lambda r: STATUS[r["status"]][0],
                demo_bg=lambda r: STATUS[r["status"]][1],
            ),
            label(
                "lblRowDate",
                "If(IsBlank(ThisItem.'Submitted On'), \"Not submitted\", "
                '"Submitted " & Text(ThisItem.\'Submitted On\', "mmm d"))',
                ("Parent.TemplateWidth - 180", list_w - 2 - 180),
                42,
                160,
                18,
                size=8.5,
                color="Subtle",
                align="Right",
                on_select="Select(Parent)",
                demo=lambda r: f"Submitted {r['date']}" if r["date"] else "Not submitted",
            ),
            rect("recRowLine", 0, 75, ("Parent.TemplateWidth", list_w - 2), 1, fill="Border"),
        ],
        template_size=76,
        rows=[dict(r, sel=i == 0) for i, r in enumerate(DEMO_REQUESTS)],
        template_fill=(
            "If(ThisItem.IsSelected, fxTheme.PrimaryTint, fxTheme.Surface)",
            lambda r: HEX["PrimaryTint"] if r["sel"] else HEX["Surface"],
        ),
    )
    list_card = container(
        "conMyRequests",
        X0,
        250,
        list_w,
        list_h,
        [
            rows,
            label(
                "lblHomeEmpty",
                'If(varHomeFilter = "All", "No requests yet. Browse the catalog to get started.", '
                '"Nothing in this view.")',
                40,
                200,
                list_w - 80,
                40,
                size=11,
                color="Muted",
                align="Center",
                visible="IsEmpty(galMyRequests.AllItems)",
                show=False,
            ),
        ],
        shadow=True,
    )

    dx, dw = X0 + list_w + 16, CW - list_w - 16  # 956, 382
    inner = dw - 40

    step_rows = [
        {"n": 1, "label": "Created", "state": "done"},
        {"n": 2, "label": "Submitted", "state": "now"},
        {"n": 3, "label": "Decision", "state": "todo"},
        {"n": 4, "label": "Completed", "state": "todo"},
    ]
    reached = f"ThisItem.N <= {SEL_STYLE}.Rank"
    bad_here = f"ThisItem.N = {SEL_STYLE}.Rank && {SEL_STYLE}.Bad"
    dot_fill = f"If({bad_here}, {SEL_STYLE}.Fg, {reached}, fxTheme.Primary, fxTheme.Border)"
    step_w = inner // 4  # 85
    dot_x = (step_w - 22) // 2
    stepper = gallery(
        "galSteps",
        "Horizontal",
        'Table({N: 1, Step: "Created"}, {N: 2, Step: "Submitted"}, {N: 3, Step: "Decision"}, {N: 4, Step: "Completed"})',
        20,
        116,
        inner,
        56,
        [
            rect(
                "recStepLeft",
                0,
                10,
                dot_x - 3,
                2,
                fill=(f"If({reached}, fxTheme.Primary, fxTheme.Border)", "#000"),
                visible="ThisItem.N > 1",
                demo_fill=lambda r: HEX["Primary"] if r["state"] != "todo" else HEX["Border"],
                show=lambda r: r["n"] > 1,
            ),
            pill(
                "pilStepDot",
                "Text(ThisItem.N)",
                dot_x,
                0,
                22,
                22,
                fg="White",
                bg=(dot_fill, "#000"),
                size=8,
                demo=lambda r: str(r["n"]),
                demo_bg=lambda r: HEX["Primary"] if r["state"] != "todo" else HEX["Border"],
                demo_fg=lambda r: HEX["White"] if r["state"] != "todo" else HEX["Muted"],
            ),
            rect(
                "recStepRight",
                dot_x + 25,
                10,
                step_w - dot_x - 25,
                2,
                fill=(f"If(ThisItem.N < {SEL_STYLE}.Rank, fxTheme.Primary, fxTheme.Border)", "#000"),
                visible="ThisItem.N < 4",
                demo_fill=lambda r: HEX["Primary"] if r["state"] == "done" else HEX["Border"],
                show=lambda r: r["n"] < 4,
            ),
            label(
                "lblStep",
                f"If(ThisItem.N = 3 && {SEL_STYLE}.Rank = 3, Text({SEL}.'Request Status'), ThisItem.Step)",
                0,
                28,
                step_w,
                18,
                size=8.5,
                color=(f"If({reached}, fxTheme.Ink, fxTheme.Subtle)", "#000"),
                align="Center",
                demo=lambda r: r["label"],
            ),
        ],
        template_size=step_w,
        rows=step_rows,
    )
    stepper["children"][3]["pv"]["color"] = lambda r: HEX["Ink"] if r["state"] != "todo" else HEX["Subtle"]

    primary_text = (
        f"Switch(\n    {SEL}.'Request Status',\n"
        f'    {st("Draft")}, "Edit draft",\n'
        f'    {st("Approved")}, "Mark completed",\n'
        '    "Request again"\n)'
    )
    primary_action = (
        f"Switch(\n    {SEL}.'Request Status',\n"
        f"    {st('Draft')},\n"
        f"        Set(varEditRequest, {SEL});\n"
        f"        Set(varCourse, LookUp('Training Courses', 'Training Course' = {SEL}.Course.'Training Course'));\n"
        "        Navigate(scrNewRequest, ScreenTransition.Cover),\n"
        f"    {st('Approved')},\n        "
        + send_command(SEL, "Complete", "Marked as completed.", "update").replace("\n", "\n        ")
        + ",\n"
        "    // A finished request can't be reopened, so start a new one for the same course.\n"
        "    // The LookUp returns blank if the course has since been retired from the catalog.\n"
        "    Set(varEditRequest, Blank());\n"
        "    Set(\n"
        "        varCourse,\n"
        f"        LookUp('Training Courses', 'Training Course' = {SEL}.Course.'Training Course' && Active = true)\n"
        "    );\n"
        "    If(\n"
        "        IsBlank(varCourse),\n"
        '        Notify("That course is no longer offered. Pick another from the catalog.", '
        "NotificationType.Warning);\n"
        "        Navigate(scrCatalog, ScreenTransition.Fade),\n"
        "        Navigate(scrNewRequest, ScreenTransition.Cover)\n"
        "    )\n)"
    )
    is_open = f"({SEL}.'Request Status' = {st('Draft')} || {SEL}.'Request Status' = {st('Submitted')})"
    has_primary = f"{SEL}.'Request Status' <> {st('Submitted')}"

    body = container(
        "conDetailBody",
        0,
        0,
        dw,
        list_h,
        [
            label(
                "lblDetailTitle",
                f"{SEL}.Title",
                20,
                18,
                inner,
                48,
                size=13.5,
                color="Ink",
                weight="Semibold",
                wrap=True,
                valign="Top",
                demo=DEMO_REQUESTS[0]["title"],
            ),
            pill(
                "pilDetailStatus",
                status_text(SEL),
                20,
                72,
                124,
                26,
                fg=(f"If({NO_COMMAND}, {SEL_STYLE}.Fg, fxTheme.Muted)", "#000"),
                bg=(f"If({NO_COMMAND}, {SEL_STYLE}.Bg, fxTheme.Canvas)", "#fff"),
                size=9.5,
                demo="Submitted",
                demo_fg=STATUS["Submitted"][0],
                demo_bg=STATUS["Submitted"][1],
            ),
            stepper,
            rect("recDetailLine1", 20, 182, inner, 1),
            caption("lblDetailCourseCap", "Course", 20, 196, inner),
            label(
                "lblDetailCourse",
                f"{SEL}.Course.Name",
                20,
                214,
                inner,
                22,
                size=10.5,
                color="Ink",
                demo="AWS Solutions Architect Associate Bootcamp",
            ),
            caption("lblDetailCostCap", "Cost", 20, 248, 160),
            label(
                "lblDetailCost",
                f"If(IsBlank({SEL}.'Course Cost'), \"Set on submit\", " + money(f"{SEL}.'Course Cost'") + ")",
                20,
                266,
                160,
                22,
                size=10.5,
                color="Ink",
                demo="$1,450",
            ),
            caption("lblDetailSubmittedCap", "Submitted", 196, 248, 166),
            label(
                "lblDetailSubmitted",
                f"If(IsBlank({SEL}.'Submitted On'), \"Not yet\", Text({SEL}.'Submitted On', \"mmm d, yyyy\"))",
                196,
                266,
                166,
                22,
                size=10.5,
                color="Ink",
                demo="Sep 8, 2026",
            ),
            caption("lblDetailWaitingCap", "Waiting on", 20, 300, inner),
            label(
                "lblDetailWaiting",
                f"If(\n    {SEL}.'Request Status' = {st('Submitted')} && !IsBlank({SEL}.'Pending With'),\n"
                f"    {SEL}.'Pending With',\n"
                f"    {SEL}.'Request Status' = {st('Draft')},\n"
                '    "You. This request hasn\'t been submitted.",\n'
                '    "Nobody. This request is closed."\n)',
                20,
                318,
                inner,
                22,
                size=10.5,
                color="Ink",
                demo="morgan.lee@contoso.com",
            ),
            caption("lblDetailNotesCap", "Decision notes", 20, 352, inner),
            label(
                "lblDetailNotes",
                f"If(\n    !{NO_COMMAND},\n"
                '    "Working on it. This usually takes a few seconds.",\n'
                f"    Coalesce({SEL}.'Decision Comments', \"None yet.\")\n)",
                20,
                370,
                inner,
                52,
                size=10,
                color="Body",
                wrap=True,
                valign="Top",
                demo="None yet.",
            ),
            button(
                "btnDetailPrimary",
                primary_text,
                20,
                list_h - 60,
                (inner - 12) // 2,
                40,
                on_select=primary_action,
                visible=f"{NO_COMMAND} && {has_primary}",
                demo="Edit draft",
                show=False,
            ),
            button(
                "btnDetailWithdraw",
                f'If({SEL}.\'Request Status\' = {st("Draft")}, "Discard", "Withdraw request")',
                (
                    f"If({has_primary}, {20 + (inner - 12) // 2 + 12}, 20)",
                    20,
                ),
                list_h - 60,
                (inner - 12) // 2,
                40,
                kind="danger",
                on_select=send_command(SEL, "Withdraw", "Request withdrawn.", "withdraw"),
                visible=f"{NO_COMMAND} && {is_open}",
                demo="Withdraw request",
            ),
        ],
        fill=TRANSPARENT,
        border=None,
        radius=0,
        visible=f"!IsBlank({SEL})",
    )
    detail_card = container(
        "conDetail",
        dx,
        250,
        dw,
        list_h,
        [
            body,
            label(
                "lblDetailEmpty",
                q("Select a request to see where it stands."),
                30,
                210,
                dw - 60,
                40,
                size=10.5,
                color="Subtle",
                align="Center",
                wrap=True,
                visible=f"IsBlank({SEL})",
                show=False,
            ),
        ],
        shadow=True,
    )

    children = [
        sidebar("Home", "Home"),
        *page_header(
            "Home",
            '"Welcome back, " & First(Split(User().FullName, " ")).Value',
            q("Track the training you've asked for and what happens next."),
            title_demo="Welcome back, Jaden",
        ),
        container(
            "conHomeRefresh",
            W - PAD - 164 - 12 - 40,
            30,
            40,
            40,
            [
                icon(
                    "imgHomeRefresh",
                    "Refresh",
                    10,
                    10,
                    20,
                    on_select="Refresh('Training Requests')",
                    tooltip="Refresh",
                )
            ],
            radius=8,
        ),
        button(
            "btnNewRequest",
            q("+  New request"),
            W - PAD - 164,
            30,
            164,
            40,
            on_select="Navigate(scrCatalog, ScreenTransition.Fade)",
        ),
        *kpi_cards,
        filters,
        list_card,
        detail_card,
        timer(
            "tmrPoll",
            start="varPolling",
            repeat="varPolling",
            duration=4000,
            on_end=(
                "Refresh('Training Requests');\n"
                "Set(varPollTicks, varPollTicks + 1);\n"
                "// Stop once every command has been handled, or after a minute if a flow is down.\n"
                "If(\n"
                "    varPollTicks >= 15\n"
                "        || IsEmpty(Filter(galMyRequests.AllItems, !IsBlank('Requested Action'))),\n"
                "    Set(varPolling, false)\n"
                ")"
            ),
        ),
    ]
    props = {
        "Fill": tok("Canvas")[0],
        "LoadingSpinnerColor": tok("Primary")[0],
        "OnVisible": (
            'If(IsBlank(varHomeFilter), Set(varHomeFilter, "All"));\n'
            "If(IsBlank(varPollTicks), Set(varPollTicks, 0));\n"
            "Refresh('Training Requests')"
        ),
    }
    return {"name": "scrHome", "props": props, "children": children}


# ───────────────────────── screen: Catalog ─────────────────────────

DEMO_COURSES = [
    ("Technical", "Azure Fundamentals (AZ-900)", "Microsoft Learn", 8, 165),
    ("Technical", "AWS Solutions Architect Associate Bootcamp", "A Cloud Guru", 40, 1450),
    ("Technical", "Advanced Python for Data Engineering", "Coursera", 30, 399),
    ("Technical", "Power Platform Developer (PL-400) Prep", "Microsoft Learn", 24, 1200),
    ("Leadership", "New Manager Essentials", "LinkedIn Learning", 16, 850),
    ("Leadership", "Executive Leadership Program", "Northwind Leadership Institute", 24, 2495),
    ("Compliance", "Data Privacy and GDPR Compliance", "Compliance Academy", 6, 300),
    ("Professional Development", "Business Writing and Presentation Skills", "Contoso Learning", 12, 695),
    ("Professional Development", "PMP Certification Prep", "Contoso Learning", 35, 1895),
]


def screen_catalog() -> dict:
    cell = CW // 3  # 359
    card_w = cell - 16
    cat_fg = "LookUp(fxCategoryStyles, Key = Text(ThisItem.Category)).Fg"
    cat_bg = "LookUp(fxCategoryStyles, Key = Text(ThisItem.Category)).Bg"
    pick = (
        "Set(varEditRequest, Blank());\n"
        "Set(varCourse, ThisItem);\n"
        "Navigate(scrNewRequest, ScreenTransition.Cover)"
    )
    card = container(
        "conCourseCard",
        0,
        0,
        ("Parent.TemplateWidth - 16", card_w),
        180,
        [
            pill(
                "pilCourseCategory",
                "Text(ThisItem.Category)",
                16,
                16,
                ("Min(Parent.Width - 32, 24 + Len(Text(ThisItem.Category)) * 7)", 100),
                22,
                fg=(cat_fg, "#000"),
                bg=(cat_bg, "#fff"),
                size=8.5,
                demo=lambda r: r["cat"],
                demo_fg=lambda r: CATEGORY_HEX[r["cat"]][0],
                demo_bg=lambda r: CATEGORY_HEX[r["cat"]][1],
            ),
            label(
                "lblCourseName",
                "ThisItem.Name",
                16,
                46,
                ("Parent.Width - 32", card_w - 32),
                44,
                size=12,
                color="Ink",
                weight="Semibold",
                wrap=True,
                valign="Top",
                demo=lambda r: r["name"],
            ),
            label(
                "lblCourseMeta",
                'ThisItem.Provider & "  ·  " & ThisItem.Hours & " hrs"',
                16,
                94,
                ("Parent.Width - 32", card_w - 32),
                18,
                size=9.5,
                color="Muted",
                demo=lambda r: f"{r['provider']}  ·  {r['hours']} hrs",
            ),
            rect("recCourseLine", 16, 124, ("Parent.Width - 32", card_w - 32), 1),
            label(
                "lblCourseCost",
                'If(ThisItem.Cost = 0, "Free", ' + money("ThisItem.Cost") + ")",
                16,
                134,
                130,
                32,
                size=15,
                color="Ink",
                weight="Semibold",
                demo=lambda r: f"${r['cost']:,}" if r["cost"] else "Free",
            ),
            button(
                "btnRequestCourse",
                q("Request"),
                ("Parent.Width - 16 - 104", card_w - 16 - 104),
                134,
                104,
                34,
                on_select=pick,
                size=10,
            ),
        ],
        shadow=True,
    )
    card["children"][0]["pv"]["w"] = lambda r: min(card_w - 32, 24 + len(r["cat"]) * 7)

    course_filter = (
        "Filter(\n"
        "    'Training Courses',\n"
        "    Active = true,\n"
        "    StartsWith(Name, txtSearch.Text),\n"
        "    IsBlank(varCategory) || Category = varCategory\n"
        ")"
    )
    grid = gallery(
        "galCourses",
        "Vertical",
        course_filter,
        X0,
        164,
        CW + 8,
        H - 164 - 12,
        [card],
        template_size=196,
        wrap=3,
        rows=[{"cat": c, "name": n, "provider": p, "hours": h, "cost": cost} for c, n, p, h, cost in DEMO_COURSES],
    )

    chips = gallery(
        "galCategories",
        "Horizontal",
        "Choices('Category (Training Courses)')",
        X0 + 300 + 16 + 64,
        104,
        CW - 300 - 16 - 64,
        34,
        [
            button(
                "btnCategory",
                "Text(ThisItem.Value)",
                0,
                0,
                168,
                32,
                kind="secondary",
                on_select="Set(varCategory, ThisItem.Value)",
                size=9.5,
                demo=lambda r: r["label"],
            )
        ],
        template_size=172,
        rows=[{"label": c} for c in CATEGORY_HEX],
    )
    chip = chips["children"][0]
    chip["props"] |= {
        "Fill": "If(ThisItem.Value = varCategory, fxTheme.Ink, fxTheme.Surface)",
        "Color": "If(ThisItem.Value = varCategory, fxTheme.White, fxTheme.Body)",
        "HoverColor": "If(ThisItem.Value = varCategory, fxTheme.White, fxTheme.Ink)",
        "HoverFill": "If(ThisItem.Value = varCategory, fxTheme.Ink, fxTheme.SurfaceAlt)",
        "RadiusTopLeft": "16",
        "RadiusTopRight": "16",
        "RadiusBottomLeft": "16",
        "RadiusBottomRight": "16",
    }
    chip["pv"] |= {"radius": 16}

    all_chip = button(
        "btnCategoryAll",
        q("All"),
        X0 + 300 + 16,
        104,
        56,
        32,
        kind="secondary",
        on_select="Set(varCategory, Blank())",
        size=9.5,
    )
    all_chip["props"] |= {
        "Fill": "If(IsBlank(varCategory), fxTheme.Ink, fxTheme.Surface)",
        "Color": "If(IsBlank(varCategory), fxTheme.White, fxTheme.Body)",
        "HoverColor": "If(IsBlank(varCategory), fxTheme.White, fxTheme.Ink)",
        "HoverFill": "If(IsBlank(varCategory), fxTheme.Ink, fxTheme.SurfaceAlt)",
        "RadiusTopLeft": "16",
        "RadiusTopRight": "16",
        "RadiusBottomLeft": "16",
        "RadiusBottomRight": "16",
    }
    all_chip["pv"] |= {"radius": 16, "fill": HEX["Ink"], "color": HEX["White"]}

    children = [
        sidebar("Catalog", "Catalog"),
        *page_header(
            "Catalog",
            q("Course catalog"),
            q("Pick a course to request. Courses over the cost threshold need a second approval."),
        ),
        container(
            "conSearch",
            X0,
            100,
            300,
            40,
            [
                icon("imgSearch", "Search", 12, 11, 18, stroke="Subtle"),
                text_input("txtSearch", q(""), 36, 2, 260, 36, hint="Search courses by name", borderless=True),
            ],
            radius=8,
        ),
        all_chip,
        chips,
        grid,
        label(
            "lblCatalogEmpty",
            q("No courses match. Try a different search or category."),
            X0,
            300,
            CW,
            40,
            size=11,
            color="Muted",
            align="Center",
            visible="IsEmpty(galCourses.AllItems)",
            show=False,
        ),
    ]
    props = {"Fill": tok("Canvas")[0], "LoadingSpinnerColor": tok("Primary")[0]}
    return {"name": "scrCatalog", "props": props, "children": children}


# ───────────────────────── screen: New request ─────────────────────────


def screen_new_request() -> dict:
    fw, fh = 660, H - 110 - 24  # 660 x 634
    inner = fw - 48
    needs = "varCourse.Cost > varThreshold"
    is_new = "IsBlank(varEditRequest)"

    save = (
        "// One formula for both buttons: varSubmitIntent says whether to send the Submit command.\n"
        "// The app writes these four columns and no others; status, cost and approver belong to the flows.\n"
        "IfError(\n"
        "    If(\n"
        f"        {is_new},\n"
        "        Patch(\n"
        "            'Training Requests',\n"
        "            Defaults('Training Requests'),\n"
        "            {\n"
        "                Title: Trim(txtTitle.Text),\n"
        "                Course: varCourse,\n"
        "                Justification: Trim(txtJustification.Text),\n"
        "                'Requested Action': If(varSubmitIntent, fxAction.Submit, Blank())\n"
        "            }\n"
        "        ),\n"
        "        // Course is deliberately absent: it can't be changed once the draft exists.\n"
        "        Patch(\n"
        "            'Training Requests',\n"
        "            varEditRequest,\n"
        "            {\n"
        "                Title: Trim(txtTitle.Text),\n"
        "                Justification: Trim(txtJustification.Text),\n"
        "                'Requested Action': If(varSubmitIntent, fxAction.Submit, Blank())\n"
        "            }\n"
        "        )\n"
        "    );\n"
        '    Notify(If(varSubmitIntent, "Request sent for approval.", "Draft saved."), '
        "NotificationType.Success);\n"
        "    Set(varPollTicks, 0);\n"
        "    Set(varPolling, varSubmitIntent);\n"
        "    Set(varEditRequest, Blank());\n"
        "    Navigate(scrHome, ScreenTransition.Fade),\n"
        '    Notify("Could not save: " & FirstError.Message, NotificationType.Error)\n'
        ")"
    )
    submit = (
        "If(\n"
        "    IsBlank(Trim(txtTitle.Text)),\n"
        '        Notify("Give the request a title.", NotificationType.Error),\n'
        f"    {needs} && IsBlank(Trim(txtJustification.Text)),\n"
        "        Notify(\n"
        '            "Justification is required for courses over " & Text(varThreshold, "$#,##0") & ".",\n'
        "            NotificationType.Error\n"
        "        ),\n"
        "    Set(varSubmitIntent, true);\n"
        "    Select(btnSave)\n"
        ")"
    )
    draft = (
        "If(\n"
        "    IsBlank(Trim(txtTitle.Text)),\n"
        '    Notify("Give the request a title.", NotificationType.Error),\n'
        "    Set(varSubmitIntent, false);\n"
        "    Select(btnSave)\n"
        ")"
    )
    estimate = (
        "IfError(\n"
        "    Set(varEstimate, TrainingEstimate.GetEstimate(varCourse.Cost, varCourse.Hours)),\n"
        "    Set(varEstimate, Blank())\n"
        ");\n"
        "// The API owns the threshold. Fall back to the local constant only when it didn't answer.\n"
        "Set(varThreshold, Coalesce(varEstimate.high_cost_threshold, fxFallbackThreshold))"
    )

    form = container(
        "conForm",
        X0,
        110,
        fw,
        fh,
        [
            caption("lblFormCourseCap", "Course", 24, 22, inner),
            container(
                "conFormCourse",
                24,
                44,
                inner,
                72,
                [
                    label(
                        "lblFormCourseName",
                        "varCourse.Name",
                        16,
                        12,
                        inner - 150,
                        24,
                        size=12,
                        color="Ink",
                        weight="Semibold",
                        demo="Executive Leadership Program",
                    ),
                    label(
                        "lblFormCourseMeta",
                        'varCourse.Provider & "  ·  " & Text(varCourse.Category) & "  ·  " & varCourse.Hours & " hrs"',
                        16,
                        38,
                        inner - 150,
                        20,
                        size=9.5,
                        color="Muted",
                        demo="Northwind Leadership Institute  ·  Leadership  ·  24 hrs",
                    ),
                    label(
                        "lblFormCourseChange",
                        q("Change course"),
                        inner - 126,
                        24,
                        110,
                        24,
                        size=10,
                        color="Primary",
                        weight="Semibold",
                        align="Right",
                        on_select="Navigate(scrCatalog, ScreenTransition.UnCover)",
                        visible=is_new,
                    ),
                ],
                fill="SurfaceAlt",
                radius=8,
            ),
            caption("lblFormTitleCap", "Request title", 24, 136, inner),
            text_input(
                "txtTitle",
                f"If({is_new}, varCourse.Name, varEditRequest.Title)",
                24,
                158,
                inner,
                40,
                hint="For example: PL-400 prep for the CoE backlog",
                max_length=100,
            ),
            caption("lblFormJustCap", "Business justification", 24, 218, 300),
            label(
                "lblFormJustRule",
                f'If({needs}, "Required for courses over " & Text(varThreshold, "$#,##0"), "Optional")',
                24 + inner - 280,
                216,
                280,
                20,
                size=9,
                color=(f"If({needs}, fxTheme.Warn, fxTheme.Subtle)", HEX["Warn"]),
                weight="Semibold",
                align="Right",
                demo="Required for courses over $1,000",
            ),
            text_input(
                "txtJustification",
                f'If({is_new}, "", varEditRequest.Justification)',
                24,
                240,
                inner,
                148,
                hint="What will this training let you or your team do?",
                multiline=True,
                max_length=2000,
            ),
            label(
                "lblFormJustHint",
                q("Your approver reads this in the approval request. Be specific about the outcome."),
                24,
                394,
                inner,
                18,
                size=9,
                color="Subtle",
            ),
            container(
                "conFormApprover",
                24,
                430,
                inner,
                52,
                [
                    icon("imgFormApprover", "User", 14, 15, 22, stroke="Primary"),
                    label(
                        "lblFormApprover",
                        '"Goes to " & Coalesce(fxMe.Manager.\'Full Name\', "the training team") & " for approval"',
                        48,
                        6,
                        inner - 64,
                        20,
                        size=10.5,
                        color="Ink",
                        weight="Semibold",
                        demo="Goes to Morgan Lee for approval",
                    ),
                    label(
                        "lblFormApproverSub",
                        q("Your manager is assigned automatically. You'll get an email when they decide."),
                        48,
                        26,
                        inner - 64,
                        18,
                        size=9,
                        color="Muted",
                    ),
                ],
                fill="PrimaryTint",
                border=None,
                radius=8,
            ),
            rect("recFormLine", 24, fh - 88, inner, 1),
            button(
                "btnSubmit",
                q("Submit for approval"),
                24,
                fh - 64,
                190,
                40,
                on_select=submit,
                display="If(IsBlank(varCourse), DisplayMode.Disabled, DisplayMode.Edit)",
            ),
            button(
                "btnSaveDraft",
                q("Save as draft"),
                226,
                fh - 64,
                140,
                40,
                kind="secondary",
                on_select=draft,
                display="If(IsBlank(varCourse), DisplayMode.Disabled, DisplayMode.Edit)",
            ),
            button(
                "btnCancel",
                q("Cancel"),
                fw - 24 - 100,
                fh - 64,
                100,
                40,
                kind="ghost",
                on_select="Set(varEditRequest, Blank());\nNavigate(scrHome, ScreenTransition.Fade)",
            ),
            hidden_button("btnSave", save),
            hidden_button("btnRefreshEstimate", estimate),
        ],
        shadow=True,
    )

    sx, sw = X0 + fw + 16, CW - fw - 16  # 936, 402
    s_inner = sw - 48
    second = "Coalesce(varEstimate.requires_second_approval, varCourse.Cost > varThreshold)"
    summary = container(
        "conSummary",
        sx,
        110,
        sw,
        404,
        [
            caption("lblSumCap", "Cost and approval", 24, 22, s_inner),
            label(
                "lblSumCost",
                'If(varCourse.Cost = 0, "Free", ' + money("varCourse.Cost") + ")",
                24,
                44,
                200,
                40,
                size=24,
                color="Ink",
                weight="Semibold",
                demo="$2,495",
            ),
            pill(
                "pilSumTier",
                f'If({second}, "High tier", "Standard tier")',
                sw - 24 - 116,
                52,
                116,
                26,
                fg=(f"If({second}, fxTheme.Warn, fxTheme.Good)", "#000"),
                bg=(f"If({second}, fxTheme.WarnTint, fxTheme.GoodTint)", "#fff"),
                size=9.5,
                demo="High tier",
                demo_fg=HEX["Warn"],
                demo_bg=HEX["WarnTint"],
            ),
            label(
                "lblSumRate",
                'Text(varCourse.Cost / varCourse.Hours, "$#,##0.00") & " per hour  ·  " & varCourse.Hours & " hours"',
                24,
                88,
                s_inner,
                20,
                size=10,
                color="Muted",
                demo="$103.96 per hour  ·  24 hours",
            ),
            rect("recSumLine", 24, 124, s_inner, 1),
            caption("lblSumRouteCap", "Approval route", 24, 140, s_inner),
            pill("pilSumStep1", q("1"), 24, 166, 24, 24, fg="White", bg="Primary"),
            label(
                "lblSumStep1", q("Your manager"), 60, 162, s_inner - 36, 18, size=10.5, color="Ink", weight="Semibold"
            ),
            label(
                "lblSumStep1Sub",
                "Coalesce(fxMe.Manager.'Full Name', \"Assigned by the training team\")",
                60,
                180,
                s_inner - 36,
                18,
                size=9.5,
                color="Muted",
                demo="Morgan Lee",
            ),
            pill(
                "pilSumStep2",
                q("2"),
                24,
                218,
                24,
                24,
                fg="White",
                bg=(f"If({second}, fxTheme.Primary, fxTheme.Disabled)", HEX["Primary"]),
            ),
            label(
                "lblSumStep2",
                q("Second approver"),
                60,
                214,
                s_inner - 36,
                18,
                size=10.5,
                color=(f"If({second}, fxTheme.Ink, fxTheme.Subtle)", HEX["Ink"]),
                weight="Semibold",
            ),
            label(
                "lblSumStep2Sub",
                f'If({second}, "Required because the cost is over " & Text(varThreshold, "$#,##0"), '
                '"Not needed at this cost")',
                60,
                232,
                s_inner - 36,
                18,
                size=9.5,
                color="Muted",
                demo="Required because the cost is over $1,000",
            ),
            pill("pilSumStep3", q("3"), 24, 270, 24, 24, fg="White", bg="Primary"),
            label(
                "lblSumStep3",
                q("You're told the outcome"),
                60,
                266,
                s_inner - 36,
                18,
                size=10.5,
                color="Ink",
                weight="Semibold",
            ),
            label(
                "lblSumStep3Sub",
                q("By email, and on your requests page"),
                60,
                284,
                s_inner - 36,
                18,
                size=9.5,
                color="Muted",
            ),
            label(
                "lblSumOffline",
                q(
                    "Live estimate unavailable. The route above uses the standard threshold; "
                    "the final routing is decided when you submit."
                ),
                24,
                328,
                s_inner,
                52,
                size=9,
                color="Warn",
                wrap=True,
                fill="WarnTint",
                pad=10,
                visible="IsBlank(varEstimate) && !IsBlank(varCourse)",
                show=False,
            ),
        ],
        shadow=True,
    )
    notes = container(
        "conNext",
        sx,
        110 + 404 + 16,
        sw,
        fh - 404 - 16,
        [
            caption("lblNextCap", "Good to know", 24, 20, s_inner),
            label(
                "lblNext1",
                q("Approvers have 7 days to respond, with a reminder from day 3."),
                24,
                44,
                s_inner,
                36,
                size=10,
                color="Body",
                wrap=True,
                valign="Top",
            ),
            label(
                "lblNext2",
                q("You can withdraw a request any time before it is decided."),
                24,
                84,
                s_inner,
                36,
                size=10,
                color="Body",
                wrap=True,
                valign="Top",
            ),
            label(
                "lblNext3",
                q("The course can't be changed after the first save. Discard the draft and start again instead."),
                24,
                124,
                s_inner,
                54,
                size=10,
                color="Body",
                wrap=True,
                valign="Top",
            ),
        ],
        shadow=True,
    )

    back = "Set(varEditRequest, Blank());\nNavigate(scrHome, ScreenTransition.Fade)"
    children = [
        sidebar("New", "Home"),
        icon("imgNewBack", "Back", X0, 30, 18, stroke="Muted", on_select=back, tooltip="Back to my requests"),
        label(
            "lblNewBack",
            q("My requests"),
            X0 + 26,
            28,
            200,
            22,
            size=10,
            color="Muted",
            on_select=back,
            hover_color="Ink",
        ),
        label(
            "lblTitleNew",
            f'If({is_new}, "New request", "Edit draft")',
            X0,
            56,
            640,
            36,
            size=20,
            color="Ink",
            weight="Semibold",
            demo="New request",
        ),
        form,
        summary,
        notes,
    ]
    props = {
        "Fill": tok("Canvas")[0],
        "LoadingSpinnerColor": tok("Primary")[0],
        "OnVisible": (
            "Set(varSubmitIntent, false);\n"
            "Set(varThreshold, fxFallbackThreshold);\n"
            "Reset(txtTitle);\n"
            "Reset(txtJustification);\n"
            "If(\n"
            "    IsBlank(varCourse),\n"
            "    Navigate(scrCatalog, ScreenTransition.Fade),\n"
            "    Select(btnRefreshEstimate)\n"
            ")"
        ),
    }
    return {"name": "scrNewRequest", "props": props, "children": children}


# ───────────────────────── screen: Approvals ─────────────────────────

DEMO_PENDING = [
    {
        "title": "AWS bootcamp - platform team",
        "sub": "AWS Solutions Architect Associate Bootcamp  ·  $1,450",
        "days": 6,
    },
    {"title": "Presentation skills - PM", "sub": "Business Writing and Presentation Skills  ·  $695", "days": 4},
    {"title": "AZ-900 for finance analysts", "sub": "Azure Fundamentals (AZ-900)  ·  $165", "days": 2},
    {"title": "Manager essentials - finance", "sub": "New Manager Essentials  ·  $850", "days": 1},
]

PSEL = "galPending.Selected"


def screen_approvals() -> dict:
    lw, lh = 620, H - 110 - 24
    days = "DateDiff(ThisItem.'Submitted On', Now(), TimeUnit.Days)"
    late = f"{days} >= 5"
    rows = gallery(
        "galPending",
        "Vertical",
        (
            "// Oldest first, so nothing waits forever.\n"
            "Sort(\n"
            "    Filter(\n"
            "        'Training Requests',\n"
            f"        'Request Status' = {st('Submitted')},\n"
            "        'Pending With' = fxMe.'Primary Email'\n"
            "    ),\n"
            "    'Submitted On',\n"
            "    SortOrder.Ascending\n"
            ")"
        ),
        1,
        1,
        lw - 2,
        lh - 2,
        [
            label(
                "lblPendingTitle",
                "ThisItem.Title",
                22,
                14,
                430,
                24,
                size=11.5,
                color="Ink",
                weight="Semibold",
                on_select="Select(Parent)",
                demo=lambda r: r["title"],
            ),
            label(
                "lblPendingSub",
                'ThisItem.Course.Name & "  ·  " & ' + money("ThisItem.'Course Cost'"),
                22,
                40,
                430,
                20,
                size=9.5,
                color="Muted",
                on_select="Select(Parent)",
                demo=lambda r: r["sub"],
            ),
            pill(
                "pilPendingAge",
                f'If({days} = 0, "Today", {days} = 1, "1 day", {days} & " days")',
                ("Parent.TemplateWidth - 116", lw - 2 - 116),
                25,
                96,
                24,
                fg=(f"If({late}, fxTheme.Danger, fxTheme.Muted)", "#000"),
                bg=(f"If({late}, fxTheme.DangerTint, fxTheme.Canvas)", "#fff"),
                demo=lambda r: f"{r['days']} days" if r["days"] != 1 else "1 day",
                demo_fg=lambda r: HEX["Danger"] if r["days"] >= 5 else HEX["Muted"],
                demo_bg=lambda r: HEX["DangerTint"] if r["days"] >= 5 else HEX["Canvas"],
            ),
            rect("recPendingLine", 0, 75, ("Parent.TemplateWidth", lw - 2), 1),
        ],
        template_size=76,
        rows=[dict(r, sel=i == 0) for i, r in enumerate(DEMO_PENDING)],
        template_fill=(
            "If(ThisItem.IsSelected, fxTheme.PrimaryTint, fxTheme.Surface)",
            lambda r: HEX["PrimaryTint"] if r["sel"] else HEX["Surface"],
        ),
    )
    list_card = container(
        "conPending",
        X0,
        110,
        lw,
        lh,
        [
            rows,
            label(
                "lblPendingEmpty",
                q("You're all caught up. Nothing is waiting for your decision."),
                40,
                260,
                lw - 80,
                40,
                size=11,
                color="Muted",
                align="Center",
                visible="IsEmpty(galPending.AllItems)",
                show=False,
            ),
        ],
        shadow=True,
    )

    dx, dw = X0 + lw + 16, CW - lw - 16  # 896, 442
    inner = dw - 48
    requester = f"If(IsType({PSEL}.Owner, Users), AsType({PSEL}.Owner, Users).'Full Name', \"A team\")"
    body = container(
        "conReviewBody",
        0,
        0,
        dw,
        lh,
        [
            label(
                "lblReviewTitle",
                f"{PSEL}.Title",
                24,
                20,
                inner,
                48,
                size=13.5,
                color="Ink",
                weight="Semibold",
                wrap=True,
                valign="Top",
                demo=DEMO_PENDING[0]["title"],
            ),
            icon("imgReviewUser", "User", 24, 74, 18, stroke="Muted"),
            label(
                "lblReviewRequester",
                f'"Requested by " & {requester}',
                48,
                72,
                inner - 24,
                22,
                size=10,
                color="Muted",
                demo="Requested by Priya Shah",
            ),
            rect("recReviewLine1", 24, 108, inner, 1),
            caption("lblReviewCourseCap", "Course", 24, 122, inner),
            label(
                "lblReviewCourse",
                f"{PSEL}.Course.Name",
                24,
                140,
                inner,
                22,
                size=10.5,
                color="Ink",
                demo="AWS Solutions Architect Associate Bootcamp",
            ),
            caption("lblReviewCostCap", "Cost", 24, 174, 180),
            label(
                "lblReviewCost",
                money(f"{PSEL}.'Course Cost'"),
                24,
                192,
                180,
                22,
                size=10.5,
                color="Ink",
                demo="$1,450",
            ),
            caption("lblReviewSubmittedCap", "Submitted", 220, 174, 180),
            label(
                "lblReviewSubmitted",
                f"Text({PSEL}.'Submitted On', \"mmm d, yyyy\")",
                220,
                192,
                180,
                22,
                size=10.5,
                color="Ink",
                demo="Sep 8, 2026",
            ),
            caption("lblReviewJustCap", "Justification", 24, 228, inner),
            label(
                "lblReviewJust",
                f'Coalesce({PSEL}.Justification, "None given.")',
                24,
                248,
                inner,
                200,
                size=10.5,
                color="Body",
                wrap=True,
                valign="Top",
                fill="SurfaceAlt",
                pad=14,
                demo="Platform team is taking over AWS landing zone ownership in Q4.",
            ),
            label(
                "lblReviewHint",
                f"If(\n    IsBlank({PSEL}.'Approval Link'),\n"
                '    "This request has no open approval. Sample data and requests still being prepared look like this.",\n'
                '    "Opens the approval. Your answer and comments are recorded by the approval flow, "\n'
                '        & "and the requester is emailed."\n)',
                24,
                lh - 124,
                inner,
                40,
                size=9,
                color="Subtle",
                wrap=True,
                valign="Top",
                demo="Opens the approval. Your answer and comments are recorded by the approval flow, "
                "and the requester is emailed.",
            ),
            button(
                "btnReview",
                q("Review and respond"),
                24,
                lh - 68,
                inner,
                44,
                on_select=f"Launch({PSEL}.'Approval Link')",
                display=f"If(IsBlank({PSEL}.'Approval Link'), DisplayMode.Disabled, DisplayMode.Edit)",
                size=11,
            ),
        ],
        fill=TRANSPARENT,
        border=None,
        radius=0,
        visible=f"!IsBlank({PSEL})",
    )
    detail = container(
        "conReview",
        dx,
        110,
        dw,
        lh,
        [
            body,
            label(
                "lblReviewEmpty",
                q("Select a request to review it."),
                30,
                280,
                dw - 60,
                40,
                size=10.5,
                color="Subtle",
                align="Center",
                visible=f"IsBlank({PSEL})",
                show=False,
            ),
        ],
        shadow=True,
    )

    children = [
        sidebar("Approvals", "Approvals"),
        *page_header(
            "Approvals",
            q("Waiting on me"),
            q("Requests whose approval is assigned to you right now, oldest first."),
        ),
        container(
            "conPendingRefresh",
            W - PAD - 40,
            30,
            40,
            40,
            [
                icon(
                    "imgPendingRefresh",
                    "Refresh",
                    10,
                    10,
                    20,
                    on_select="Refresh('Training Requests')",
                    tooltip="Refresh",
                )
            ],
            radius=8,
        ),
        list_card,
        detail,
    ]
    props = {
        "Fill": tok("Canvas")[0],
        "LoadingSpinnerColor": tok("Primary")[0],
        "OnVisible": (
            "// UX guard only. Dataverse security roles decide who can read which rows.\n"
            "If(!fxIsManager, Navigate(scrHome, ScreenTransition.Fade), Refresh('Training Requests'))"
        ),
    }
    return {"name": "scrApprovals", "props": props, "children": children}


# ───────────────────────── App.Formulas ─────────────────────────


def app_formulas() -> str:
    def record(name: str, pairs: list[tuple[str, str]]) -> str:
        width = max(len(k) for k, _ in pairs)
        body = ",\n".join(f"    {k + ':':<{width + 1}} {v}" for k, v in pairs)
        return f"{name} = {{\n{body}\n}};"

    statuses = [k for k, *_ in STATUS_STYLES]
    styles = ",\n".join(
        f"    {{ Key: {q(k)}, Fg: ColorValue({q(fg)}), Bg: ColorValue({q(bg)}), Rank: {rank}, "
        f"Bad: {str(bad).lower()} }}"
        for k, fg, bg, rank, bad in STATUS_STYLES
    )
    categories = ",\n".join(
        f"    {{ Key: {q(k)}, Fg: ColorValue({q(fg)}), Bg: ColorValue({q(bg)}) }}"
        for k, (fg, bg) in CATEGORY_HEX.items()
    )

    def mine(*keys: str) -> str:
        cond = " || ".join(f"'Request Status' = fxStatus.{k}" for k in keys)
        return f"Filter('Training Requests', Owner = fxMe, {cond})"

    return (
        "\n\n".join(
            [
                "// Training Portal: named formulas. Paste the whole file into App.Formulas.\n"
                "// Generated by powerapps/source/generate.py. Named formulas are evaluated lazily and\n"
                "// cached, so nothing here slows down app start.",
                "// ── Who is signed in ──────────────────────────────────────────────\n"
                "// Matched on the Entra object ID. Matching on email breaks when a user's sign-in\n"
                "// name and primary email differ.\n"
                "fxMe = LookUp(Users, 'Azure AD Object ID' = User().EntraObjectId);",
                "// Shows the Approvals screen. UX only: Dataverse security roles decide who can read\n"
                "// which rows. Sees roles assigned directly to the user, not through a team.\n"
                "fxIsManager =\n"
                "    !IsEmpty(\n"
                "        Filter(\n"
                "            fxMe.'Security Roles (systemuserroles_association)',\n"
                '            Name in ["Training Manager", "Training Admin", "System Administrator"]\n'
                "        )\n"
                "    );",
                "fxInitials =\n"
                "    Upper(\n"
                "        Left(User().FullName, 1)\n"
                '            & Mid(User().FullName, Find(" ", User().FullName & " ") + 1, 1)\n'
                "    );",
                "// ── Choice values ────────────────────────────────────────────────\n"
                "// Every screen goes through these two records. If Studio's IntelliSense shows a\n"
                "// different enum name for your choice columns, this is the only place to change it.\n"
                + record(
                    "fxStatus",
                    [(k, f"'Request Status (Training Requests)'.{k}") for k in statuses],
                ),
                record(
                    "fxAction",
                    [(k, f"'Requested Action (Training Requests)'.{k}") for k in ("Submit", "Withdraw", "Complete")],
                ),
                "// Used only while the estimate API is unreachable. The API's high_cost_threshold is the\n"
                '// source of truth; see "The $1,000 threshold" in dataverse/schema.md.\n'
                "fxFallbackThreshold = 1000;",
                "// ── Numbers on the home screen ───────────────────────────────────\n"
                f"fxKpiInReview = CountRows({mine('Submitted')});\n"
                f"fxKpiApproved = CountRows({mine('Approved', 'Completed')});\n"
                f"fxKpiDrafts = CountRows({mine('Draft')});\n"
                f"fxKpiSpend = Sum({mine('Approved', 'Completed')}, 'Course Cost');",
                "// Badge on the Approvals nav item: approvals assigned to me right now.\n"
                "fxPendingCount =\n"
                "    CountRows(\n"
                "        Filter(\n"
                "            'Training Requests',\n"
                "            'Request Status' = fxStatus.Submitted,\n"
                "            'Pending With' = fxMe.'Primary Email'\n"
                "        )\n"
                "    );",
                "// ── Theme ────────────────────────────────────────────────────────\n"
                "// One palette for the whole app. fxHex holds the values (the inline SVG icons need\n"
                "// hex text); fxTheme is the same palette as colours for control properties.\n"
                + record("fxHex", [(k, q(v)) for k, v in HEX.items()]),
                record("fxTheme", [(k, f"ColorValue(fxHex.{k})") for k in HEX]),
                "// Colours per request status, plus where the status sits on the four-step tracker\n"
                "// (Rank) and whether it ended badly (Bad), which turns that step the status colour.\n"
                f"fxStatusStyles = Table(\n{styles}\n);",
                f"fxCategoryStyles = Table(\n{categories}\n);",
                "// Icon shapes, drawn on a 24 x 24 grid. Each image control wraps one in an <svg> element\n"
                "// with its own stroke colour, so the app carries no image files.\n"
                + record("fxIcon", [(k, q(v)) for k, v in ICONS.items()]),
            ]
        )
        + "\n"
    )


# ───────────────────────── YAML writer ─────────────────────────


def needs_block(formula: str) -> bool:
    """YAML plain scalars can't hold a newline, ': ' or ' #'. Those formulas go in a |- block."""
    return (
        "\n" in formula
        or ": " in formula
        or " #" in formula
        or formula.endswith(":")
        or formula != formula.strip()
        or formula == ""
    )


def emit_props(props: dict, indent: int) -> list[str]:
    pad = " " * indent
    lines = []
    for key in sorted(props):
        formula = props[key]
        if needs_block(formula):
            lines.append(f"{pad}{key}: |-")
            body = ("=" + formula).split("\n")
            lines += [f"{pad}  {line}".rstrip() for line in body]
        else:
            lines.append(f"{pad}{key}: ={formula}")
    return lines


def emit_control(ctrl: dict, indent: int) -> list[str]:
    pad = " " * indent
    lines = [f"{pad}- {ctrl['name']}:", f"{pad}    Control: {ctrl['control']}"]
    if ctrl["variant"]:
        lines.append(f"{pad}    Variant: {ctrl['variant']}")
    lines.append(f"{pad}    Properties:")
    lines += emit_props(ctrl["props"], indent + 6)
    if ctrl["children"]:
        lines.append(f"{pad}    Children:")
        for child in ctrl["children"]:
            lines += emit_control(child, indent + 6)
    return lines


def emit_screen(screen: dict) -> str:
    lines = [
        f"# {screen['name']}: generated by powerapps/source/generate.py. Edit the generator, not this file.",
        "# Paste into Power Apps Studio: Tree view → right-click → Paste code. See README.md.",
        "Screens:",
        f"  {screen['name']}:",
        "    Properties:",
        *emit_props(screen["props"], 6),
        "    Children:",
    ]
    for child in screen["children"]:
        lines += emit_control(child, 6)
    return "\n".join(lines) + "\n"


# ───────────────────────── HTML preview ─────────────────────────


def val(v, row):
    return v(row) if callable(v) else v


def svg(key: str, stroke: str, size: int) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='{size}' height='{size}' fill='none' "
        f"stroke='{stroke}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{ICONS[key]}</svg>"
    )


def render(ctrl: dict, row=None) -> str:
    pv = ctrl["pv"]
    kind = pv.get("kind")
    if kind == "hidden" or not val(pv.get("show", True), row):
        return ""
    x, y, w, h = (val(pv.get(k, 0), row) for k in "xywh")
    box = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;"
    pt = "font-size:{}pt;"

    if kind == "label":
        style = box + pt.format(pv["size"]) + f"color:{val(pv['color'], row)};"
        style += f"font-weight:{600 if pv['weight'] == 'Semibold' else 400};"
        style += f"text-align:{(pv['align'] or 'Left').lower()};padding:0 {pv['pad']}px;"
        if pv["fill"]:
            style += f"background:{pv['fill']};border-radius:6px;"
        if pv["wrap"]:
            style += "white-space:normal;line-height:1.35;" + (f"padding-top:{pv['pad']}px;" if pv["pad"] else "")
            inner = f"<span>{html.escape(val(pv['text'], row))}</span>"
        else:
            style += "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" + f"line-height:{h}px;"
            inner = html.escape(val(pv["text"], row))
        valign = "flex-start" if pv["valign"] == "Top" else "center"
        if pv["wrap"]:
            style += f"display:flex;align-items:{valign};"
        return f"<div class='c' style='{style}'>{inner}</div>"

    if kind == "button":
        style = box + pt.format(pv["size"]) + f"background:{val(pv['fill'], row)};color:{val(pv['color'], row)};"
        style += f"border-radius:{pv['radius']}px;line-height:{h}px;"
        if pv["border"]:
            style += f"box-shadow:inset 0 0 0 1px {pv['border']};"
        return f"<div class='c b' style='{style}'>{html.escape(val(pv['text'], row))}</div>"

    if kind == "rect":
        return f"<div class='c' style='{box}background:{val(pv['fill'], row)};'></div>"

    if kind == "icon":
        return f"<div class='c' style='{box}'>{svg(pv['icon'], pv['stroke'], w)}</div>"

    if kind == "input":
        style = box + "color:#8A97AB;font-size:11pt;padding:0 12px;"
        style += f"line-height:{40 if pv['multiline'] else h}px;"
        if not pv["borderless"]:
            style += "background:#fff;border-radius:8px;box-shadow:inset 0 0 0 1px #E3E8EF;"
        return f"<div class='c' style='{style}'>{html.escape(pv['hint'])}</div>"

    if kind == "container":
        style = box + f"background:{pv['fill']};border-radius:{pv['radius']}px;"
        if pv["border"]:
            style += f"box-shadow:inset 0 0 0 1px {pv['border']}" + (
                ", 0 1px 3px rgba(15,27,45,.08);" if pv["shadow"] else ";"
            )
        return f"<div class='c' style='{style}'>{''.join(render(c, row) for c in ctrl['children'])}</div>"

    if kind == "gallery":
        cells = []
        size, wrap = pv["template"], pv["wrap"]
        for i, r in enumerate(pv["rows"]):
            if pv["variant"] == "Horizontal":
                cx, cy, cw, chh = i * size, 0, size, h
            else:
                cw = w // wrap
                cx, cy, chh = (i % wrap) * cw, (i // wrap) * size, size
            fill = val(pv["template_fill"], r) or "transparent"
            inner = "".join(render(c, r) for c in ctrl["children"])
            cells.append(
                f"<div class='c' style='left:{cx}px;top:{cy}px;width:{cw}px;height:{chh}px;background:{fill};'>"
                f"{inner}</div>"
            )
        return f"<div class='c' style='{box}overflow:hidden;'>{''.join(cells)}</div>"

    raise ValueError(f"no preview for {ctrl['name']} ({kind})")


def emit_preview(screens: list[dict]) -> str:
    stages = []
    for s in screens:
        body = "".join(render(c) for c in s["children"])
        stages.append(f"<h2>{s['name']}</h2><div class='stage'>{body}</div>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Training Portal: design preview</title>
<style>
  body {{ margin: 0; padding: 32px; background: #1c2230; font-family: 'Segoe UI', -apple-system, 'Helvetica Neue', Arial, sans-serif; }}
  h1 {{ color: #fff; font-size: 18px; margin: 0 0 6px; }}
  p {{ color: #aab4c5; font-size: 13px; margin: 0 0 28px; max-width: 900px; line-height: 1.5; }}
  h2 {{ color: #aab4c5; font-size: 13px; font-weight: 600; margin: 0 0 10px; letter-spacing: .04em; }}
  .stage {{ position: relative; width: {W}px; height: {H}px; background: {HEX["Canvas"]}; overflow: hidden;
            border-radius: 6px; margin-bottom: 40px; box-shadow: 0 10px 40px rgba(0,0,0,.4); }}
  .c {{ position: absolute; box-sizing: border-box; }}
  .b {{ text-align: center; font-weight: 600; white-space: nowrap; overflow: hidden; }}
</style>
</head>
<body>
<h1>Training Portal: design preview</h1>
<p>A static mock generated from the same control tree as the Power Apps YAML, with sample data in place of
formulas. It shows layout, colour and type. It is not the app: nothing here is clickable, and fonts and
spacing will differ slightly in Power Apps Studio.</p>
{"".join(stages)}
</body>
</html>
"""


# ───────────────────────── main ─────────────────────────


def build() -> dict[str, str]:
    screens = [screen_home(), screen_catalog(), screen_new_request(), screen_approvals()]
    files = {f"{s['name']}.pa.yaml": emit_screen(s) for s in screens}
    files["App.Formulas.fx"] = app_formulas()
    files["preview.html"] = emit_preview(screens)
    return files


if __name__ == "__main__":
    for name, content in build().items():
        (OUT / name).write_text(content, encoding="utf-8")
        print(f"wrote {name} ({len(content.splitlines())} lines)")
