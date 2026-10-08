"""Checks on the generated canvas app source that don't need Power Apps Studio.

They can't prove Studio will accept the screens, but they catch the mistakes that are
cheap to make and tedious to find after pasting: a formula that isn't valid YAML, a
reference to a control or named formula that doesn't exist, a property name that isn't
real, or two controls drawn on top of each other.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

import generate

SOURCE = Path(generate.__file__).parent

# Control types and properties taken from real Studio exports (pnp/powerplatform-snippets and
# Microsoft's PowerApps-Tooling samples), plus standard classic properties those samples happen
# not to use. A property outside this list is more likely a typo than a discovery.
ALLOWED = {
    "Label": {
        "Align", "BorderThickness", "Color", "Fill", "FocusedBorderThickness", "Font", "FontWeight", "Height",
        "HoverColor", "OnSelect", "PaddingBottom", "PaddingLeft", "PaddingRight", "PaddingTop", "Size", "Text",
        "VerticalAlign", "Visible", "Width", "Wrap", "X", "Y",
    },
    "Classic/Button": {
        "BorderColor", "BorderThickness", "Color", "DisabledBorderColor", "DisabledColor", "DisabledFill",
        "DisplayMode", "Fill", "FocusedBorderColor", "FocusedBorderThickness", "Font", "FontWeight", "Height",
        "HoverBorderColor", "HoverColor", "HoverFill", "OnSelect", "PaddingBottom", "PaddingLeft", "PaddingRight",
        "PaddingTop", "PressedBorderColor", "PressedColor", "PressedFill", "RadiusBottomLeft", "RadiusBottomRight",
        "RadiusTopLeft", "RadiusTopRight", "Size", "Text", "Visible", "Width", "X", "Y",
    },
    "Classic/TextInput": {
        "BorderColor", "BorderThickness", "Color", "Default", "Fill", "FocusedBorderColor",
        "FocusedBorderThickness", "Font", "Height", "HintText", "HoverBorderColor", "HoverFill", "MaxLength",
        "Mode", "OnChange", "PaddingBottom", "PaddingLeft", "PaddingRight", "PaddingTop", "RadiusBottomLeft",
        "RadiusBottomRight", "RadiusTopLeft", "RadiusTopRight", "Size", "Width", "X", "Y",
    },
    "Rectangle": {
        "BorderThickness", "Fill", "FocusedBorderThickness", "Height", "HoverFill", "PressedFill", "Visible",
        "Width", "X", "Y",
    },
    "Image": {
        "AccessibleLabel", "BorderThickness", "FocusedBorderThickness", "Height", "Image", "ImagePosition",
        "OnSelect", "Tooltip", "Visible", "Width", "X", "Y",
    },
    "GroupContainer": {
        "BorderColor", "BorderThickness", "DropShadow", "Fill", "Height", "RadiusBottomLeft", "RadiusBottomRight",
        "RadiusTopLeft", "RadiusTopRight", "Visible", "Width", "X", "Y",
    },
    "Gallery": {
        "BorderThickness", "DelayItemLoading", "Height", "Items", "LoadingSpinner", "ShowScrollbar",
        "TemplateFill", "TemplatePadding", "TemplateSize", "Width", "WrapCount", "X", "Y",
    },
    "Timer": {"AutoStart", "Duration", "OnTimerEnd", "Repeat", "Start", "Visible", "X", "Y"},
}  # fmt: skip
VARIANTS = {"GroupContainer": {"ManualLayout"}, "Gallery": {"Vertical", "Horizontal"}}
SCREEN_PROPS = {"Fill", "LoadingSpinnerColor", "OnVisible"}


class Loader(yaml.SafeLoader):
    """PyYAML reads a bare "=" as a special tag; Power Apps YAML means it literally."""


Loader.add_constructor("tag:yaml.org,2002:value", lambda loader, n: loader.construct_scalar(n))


@pytest.fixture(scope="module")
def files() -> dict[str, str]:
    return generate.build()


@pytest.fixture(scope="module")
def screens() -> list[dict]:
    return [
        generate.screen_home(),
        generate.screen_catalog(),
        generate.screen_new_request(),
        generate.screen_approvals(),
    ]


def walk(children):
    for ctrl in children:
        yield ctrl
        yield from walk(ctrl["children"])


def all_controls(screens):
    for screen in screens:
        yield from walk(screen["children"])


def all_formulas(screens, files):
    """Every formula in the app, labelled with where it lives."""
    for screen in screens:
        for prop, formula in screen["props"].items():
            yield f"{screen['name']}.{prop}", formula
        for ctrl in walk(screen["children"]):
            for prop, formula in ctrl["props"].items():
                yield f"{ctrl['name']}.{prop}", formula
    yield "App.Formulas", files["App.Formulas.fx"]


def strip_strings_and_comments(formula: str) -> str:
    """Remove string literals and // comments so identifiers and brackets can be scanned."""
    out, i = [], 0
    while i < len(formula):
        ch = formula[i]
        if ch == '"':
            i += 1
            while i < len(formula):
                if formula[i] == '"' and formula[i + 1 : i + 2] == '"':
                    i += 2
                elif formula[i] == '"':
                    break
                else:
                    i += 1
            out.append('""')
        elif formula.startswith("//", i):
            while i < len(formula) and formula[i] != "\n":
                i += 1
            continue
        elif ch == "'":
            end = formula.index("'", i + 1)
            out.append("'x'")
            i = end
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# ---------- files on disk ----------


def test_committed_files_match_the_generator(files):
    for name, content in files.items():
        on_disk = (SOURCE / name).read_text(encoding="utf-8")
        assert on_disk == content, f"{name} is stale: run python powerapps/source/generate.py"


# ---------- YAML ----------


def test_yaml_round_trips_every_formula(files, screens):
    """What Studio will read back out of each file is exactly the formula that was written."""
    for screen in screens:
        doc = yaml.load(files[f"{screen['name']}.pa.yaml"], Loader=Loader)  # noqa: S506 (Loader subclasses SafeLoader)
        assert list(doc) == ["Screens"]
        assert list(doc["Screens"]) == [screen["name"]]
        body = doc["Screens"][screen["name"]]
        assert body["Properties"] == {k: "=" + v for k, v in screen["props"].items()}

        def compare(parsed, expected):
            assert len(parsed) == len(expected)
            for item, ctrl in zip(parsed, expected, strict=True):
                assert list(item) == [ctrl["name"]]
                got = item[ctrl["name"]]
                assert got["Control"] == ctrl["control"]
                assert got.get("Variant") == ctrl["variant"]
                assert got["Properties"] == {k: "=" + v for k, v in ctrl["props"].items()}, ctrl["name"]
                compare(got.get("Children", []), ctrl["children"])

        compare(body["Children"], screen["children"])


def test_no_tabs_or_trailing_whitespace(files):
    for name, content in files.items():
        if name.endswith(".pa.yaml"):
            assert "\t" not in content, name
            assert not re.search(r"[ ]+$", content, re.M), name


# ---------- controls ----------


def test_control_names_are_unique_across_the_app(screens):
    names = [c["name"] for c in all_controls(screens)] + [s["name"] for s in screens]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, dupes


def test_control_names_are_plain_identifiers(screens):
    for ctrl in all_controls(screens):
        assert re.fullmatch(r"[a-z]{3}[A-Z]\w*", ctrl["name"]), ctrl["name"]


def test_only_known_controls_variants_and_properties(screens):
    for screen in screens:
        assert set(screen["props"]) <= SCREEN_PROPS
    for ctrl in all_controls(screens):
        assert ctrl["control"] in ALLOWED, ctrl["name"]
        assert ctrl["variant"] in VARIANTS.get(ctrl["control"], {None}), ctrl["name"]
        unknown = set(ctrl["props"]) - ALLOWED[ctrl["control"]]
        assert not unknown, (ctrl["name"], unknown)


def test_every_visible_control_has_explicit_geometry(screens):
    for ctrl in all_controls(screens):
        if ctrl["pv"].get("kind") == "hidden":
            continue
        assert {"X", "Y", "Width", "Height"} <= set(ctrl["props"]), ctrl["name"]


# ---------- formulas ----------


def test_formulas_have_balanced_brackets_and_quotes(screens, files):
    pairs = {")": "(", "]": "[", "}": "{"}
    for where, formula in all_formulas(screens, files):
        assert formula.count('"') % 2 == 0, where
        stack = []
        for ch in strip_strings_and_comments(formula):
            if ch in "([{":
                stack.append(ch)
            elif ch in pairs:
                assert stack and stack.pop() == pairs[ch], where
        assert not stack, where


def test_formulas_reference_only_things_that_exist(screens, files):
    controls = {c["name"] for c in all_controls(screens)}
    screen_names = {s["name"] for s in screens}
    defined_fx = set(re.findall(r"^(fx\w+) =", files["App.Formulas.fx"], re.M))
    everything = "\n".join(strip_strings_and_comments(f) for _, f in all_formulas(screens, files))
    assigned = set(re.findall(r"\bSet\(\s*(var\w+)", everything))

    prefixes = "btn|lbl|txt|gal|con|img|rec|pil|tmr|scr"
    for where, formula in all_formulas(screens, files):
        code = strip_strings_and_comments(formula)
        for name in re.findall(rf"\b(?:{prefixes})[A-Z]\w*", code):
            assert name in controls | screen_names, f"{where} refers to missing control {name}"
        for name in re.findall(r"\bfx[A-Z]\w*", code):
            assert name in defined_fx, f"{where} refers to undefined named formula {name}"
        for name in re.findall(r"\bvar[A-Z]\w*", code):
            assert name in assigned, f"{where} reads {name}, which nothing ever sets"


def test_named_formula_records_have_the_fields_that_are_used(screens, files):
    fx = files["App.Formulas.fx"]

    def fields(record: str) -> set[str]:
        body = re.search(rf"^{record} = \{{\n(.*?)\n\}};", fx, re.S | re.M).group(1)
        return set(re.findall(r"^\s+(\w+):", body, re.M))

    everything = "\n".join(strip_strings_and_comments(f) for _, f in all_formulas(screens, files))
    for record in ("fxTheme", "fxHex", "fxIcon", "fxStatus", "fxAction"):
        used = set(re.findall(rf"\b{record}\.(\w+)", everything))
        assert used, record
        assert used <= fields(record), (record, used - fields(record))
    assert fields("fxTheme") == fields("fxHex")


def test_every_status_has_a_style_and_a_choice(files):
    fx = files["App.Formulas.fx"]
    styled = set(re.findall(r'\{ Key: "(\w+)", Fg: .*Rank:', fx))
    choices = set(re.findall(r"'Request Status \(Training Requests\)'\.(\w+)", fx))
    expected = {"Draft", "Submitted", "Approved", "Rejected", "Completed", "Withdrawn", "Expired", "Error"}
    assert styled == choices == expected


def test_the_app_never_writes_a_flow_owned_column(screens, files):
    """Column security rejects these writes, so a Patch that includes one would fail at runtime."""
    locked = [
        "Request Status", "Approver", "Pending With", "Approval Link", "Course Cost",
        "Submitted On", "Decision Date", "Decision Comments", "Completed On",
    ]  # fmt: skip
    for where, formula in all_formulas(screens, files):
        for patch in re.findall(r"Patch\((.*?)\n\s*\)", formula, re.S) + re.findall(r"Patch\([^\n]*\)", formula):
            for column in locked:
                assert f"'{column}':" not in patch, f"{where} patches {column}"


def test_course_is_only_written_when_creating(screens):
    save = next(c for c in all_controls(screens) if c["name"] == "btnSave")["props"]["OnSelect"]
    create, edit = save.split("varEditRequest,", 1)
    assert "Course: varCourse" in create
    assert "Course:" not in edit


# ---------- icons ----------


def test_icons_are_well_formed_svg():
    for key, shape in generate.ICONS.items():
        ET.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{shape}</svg>")  # noqa: S314 (our own strings)
        assert '"' not in shape, f"{key}: double quotes would end the Power Fx string"


# ---------- layout ----------


def boxes(children):
    """Static, always-visible siblings with plain-number geometry."""
    for ctrl in children:
        pv = ctrl["pv"]
        if pv.get("kind") == "hidden" or pv.get("show", True) is not True:
            continue
        if "Visible" in ctrl["props"]:
            continue
        geometry = [pv.get(k) for k in "xywh"]
        if all(isinstance(v, int | float) for v in geometry):
            yield ctrl["name"], *geometry


def test_siblings_never_overlap(screens):
    """The design doesn't depend on z-order, so pasting can't hide one control behind another."""

    def check(children):
        placed = list(boxes(children))
        for i, (a, ax, ay, aw, ah) in enumerate(placed):
            for b, bx, by, bw, bh in placed[i + 1 :]:
                apart = ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
                assert apart, f"{a} overlaps {b}"
        for ctrl in children:
            check(ctrl["children"])

    for screen in screens:
        check(screen["children"])


def test_children_fit_inside_their_parents(screens):
    def check(parent_name, width, height, children):
        for name, x, y, w, h in boxes(children):
            assert x >= 0 and y >= 0 and x + w <= width and y + h <= height, f"{name} spills out of {parent_name}"
        for ctrl in children:
            pv = ctrl["pv"]
            if pv.get("kind") == "container" and isinstance(pv.get("w"), int | float):
                check(ctrl["name"], pv["w"], pv["h"], ctrl["children"])
            elif pv.get("kind") == "gallery":
                cell_w = pv["template"] if pv["variant"] == "Horizontal" else pv["w"] // pv["wrap"]
                cell_h = pv["h"] if pv["variant"] == "Horizontal" else pv["template"]
                check(ctrl["name"], cell_w, cell_h, ctrl["children"])

    for screen in screens:
        check(screen["name"], generate.W, generate.H, screen["children"])
