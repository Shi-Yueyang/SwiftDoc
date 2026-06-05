"""
Generate call-graph diagrams for each function.
Layout: callers (left) -> current function (center) -> callees (right).

Rendered with Pillow -- no matplotlib dependency.
"""

import json
import os
import logging
import platform

from PIL import Image, ImageDraw, ImageFont

from core.utils import iter_progress


logger = logging.getLogger(__name__)

STYLES = {
    "plain": {
        "background_color": "#ffffff",
        "center_fill": "#ffffff",
        "center_edge": "#000000",
        "center_text": "#000000",
        "caller_fill": "#ffffff",
        "caller_edge": "#000000",
        "caller_text": "#000000",
        "caller_line": "#000000",
        "callee_fill": "#ffffff",
        "callee_edge": "#000000",
        "callee_text": "#000000",
        "callee_line": "#000000",
        "rounding_size": 0.0,
        "card_linewidth": 1,
        "arrow_linewidth": 1,
    },
    "slate": {
        "background_color": "#f8fafc",
        "center_fill": "#1e293b",
        "center_edge": "#1e293b",
        "center_text": "#f8fafc",
        "caller_fill": "#fff1f2",
        "caller_edge": "#e11d48",
        "caller_text": "#881337",
        "caller_line": "#f43f5e",
        "callee_fill": "#eff6ff",
        "callee_edge": "#3b82f6",
        "callee_text": "#1e3a8a",
        "callee_line": "#60a5fa",
        "rounding_size": 0.15,
        "card_linewidth": 2,
        "arrow_linewidth": 2,
    },
    "fearless": {
        "background_color": "#fef9ef",
        "center_fill": "#ffffff",
        "center_edge": "#b8860b",
        "center_text": "#5c3d0e",
        "caller_fill": "#ffffff",
        "caller_edge": "#daa520",
        "caller_text": "#5c3d0e",
        "caller_line": "#cd9b1d",
        "callee_fill": "#ffffff",
        "callee_edge": "#8b6914",
        "callee_text": "#5c3d0e",
        "callee_line": "#a67c1e",
        "rounding_size": 0.12,
        "card_linewidth": 2,
        "arrow_linewidth": 2,
    },
    "red": {
        "background_color": "#fefcfb",
        "center_fill": "#fffaf7",
        "center_edge": "#991b1b",
        "center_text": "#450a0a",
        "caller_fill": "#ffffff",
        "caller_edge": "#dc2626",
        "caller_text": "#7f1d1d",
        "caller_line": "#ef4444",
        "callee_fill": "#ffffff",
        "callee_edge": "#7f1d1d",
        "callee_text": "#450a0a",
        "callee_line": "#991b1b",
        "rounding_size": 0.1,
        "card_linewidth": 2,
        "arrow_linewidth": 2,
    },
}

# Max characters per line before wrapping (center / side cards)
CENTER_WRAP = 35
SIDE_WRAP = 22

# Pixels per data-unit — matches DPI * 1.5 used in generate_function_graphs
PX_PER_UNIT = 270


def _measure_text_px(text, fontsize, bold=False):
    """Return (width, height) in pixels for *text* rendered at *fontsize*."""
    font = _load_font(fontsize, bold=bold)
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _hex_to_rgb(hex_color):
    """Convert '#ffffff' to (255, 255, 255) tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _load_font(size, bold=False):
    """Load a TTF font at the given point size with cross-platform fallback."""
    system = platform.system()
    if system == "Linux":
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        candidates = [
            f"/usr/share/fonts/truetype/dejavu/{name}",
            f"/usr/share/fonts/dejavu/{name}",
            f"/usr/share/fonts/TTF/{name}",
        ]
    elif system == "Windows":
        if bold:
            candidates = [
                "C:\\Windows\\Fonts\\arialbd.ttf",
                "C:\\Windows\\Fonts\\segoeuib.ttf",
            ]
        else:
            candidates = [
                "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\segoeui.ttf",
            ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    else:
        candidates = []

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue

    return ImageFont.load_default()


def _wrap_text(text, max_chars):
    """Split *text* into lines, each at most *max_chars* characters.

    Prefers breaking at underscores; falls back to hard cut.
    """
    if len(text) <= max_chars:
        return text
    lines = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break
        chunk = remaining[:max_chars]
        cut = chunk.rfind("_")
        if cut > max_chars // 2:
            lines.append(remaining[:cut + 1])
            remaining = remaining[cut + 1:]
        else:
            cut = chunk.rfind("_")
            if cut > 0:
                lines.append(remaining[:cut])
                remaining = remaining[cut + 1:]
            else:
                lines.append(remaining[:max_chars])
                remaining = remaining[max_chars:]
    return "\n".join(lines)


def estimate_text_units(text):
    weighted_length = 0.0
    for char in text:
        if char == "_":
            weighted_length += 1.3
        elif char.isupper() or char.isdigit():
            weighted_length += 1.15
        elif ord(char) > 127:
            weighted_length += 1.8
        else:
            weighted_length += 1.0
    return weighted_length


def get_box_width(text, padding=0.1, min_width=0.3, fontsize=11):
    """Return box width in data units, sized via Pillow measurement.

    Args:
        text: Display text (may contain newlines).
        padding: Extra whitespace in data units added to the measured width.
        min_width: Floor width in data units.
        fontsize: Point size of the text font.
    """
    if "\n" in text:
        widest_px = max(_measure_text_px(line, fontsize)[0] for line in text.split("\n"))
    else:
        widest_px = _measure_text_px(text, fontsize)[0]
    return max(min_width, widest_px / PX_PER_UNIT) + padding


def get_box_height(fontsize, lines=1, padding=0.2):
    """Return box height in data units, sized via Pillow measurement."""
    _, line_h_px = _measure_text_px("Ag", fontsize)
    return line_h_px * lines / PX_PER_UNIT + padding


def draw_card(draw, px, py, pw, ph, text, fill, edge, text_color, fontsize=11,
              style=None, scale=270):
    """Draw a single function card.

    Args:
        draw: ImageDraw.Draw object.
        px, py: Card center in pixel coordinates.
        pw, ph: Card width and height in pixels.
        text: Display text (may contain newlines).
        fill, edge, text_color: RGB tuples from _hex_to_rgb.
        fontsize: Point size for the text.
        style: The style dict from STYLES.
        scale: Pixels per data-unit (for converting rounding_size).
    """
    if style is None:
        style = STYLES["plain"]

    x1 = px - pw // 2
    y1 = py - ph // 2
    x2 = px + pw // 2
    y2 = py + ph // 2

    rounding = int(style["rounding_size"] * scale)
    card_linewidth = max(1, int(style["card_linewidth"]))

    if rounding > 0:
        draw.rounded_rectangle(
            [x1, y1, x2, y2], radius=rounding,
            fill=fill, outline=edge, width=card_linewidth,
        )
    else:
        draw.rectangle(
            [x1, y1, x2, y2],
            fill=fill, outline=edge, width=card_linewidth,
        )

    # Draw centered text
    font = _load_font(fontsize, bold=False)
    draw.text((px, py), text, fill=text_color, font=font, anchor="mm")


def draw_connector(draw, start, end, color, linewidth=1):
    """Draw a line with a triangular arrowhead from *start* to *end*.

    Args:
        draw: ImageDraw.Draw object.
        start, end: (x, y) pixel coordinate tuples.
        color: RGB tuple.
        linewidth: Line thickness in pixels.
    """
    sx, sy = start
    ex, ey = end

    dx = ex - sx
    dy = ey - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1:
        return

    nx = dx / length
    ny = dy / length

    arrow_size = 20 + linewidth * 2
    lw = max(1, int(linewidth))

    # Push past nominal endpoints by half linewidth so the square
    # cap overlaps the card border and blends into the arrowhead.
    overlap = lw / 2
    sx_a = sx + nx * overlap
    sy_a = sy + ny * overlap
    ex_a = ex - nx * overlap
    ey_a = ey - ny * overlap

    # Shaft -- stop short of arrowhead tip
    shaft_end = (ex_a - nx * arrow_size * 0.35, ey_a - ny * arrow_size * 0.35)
    draw.line([(sx_a, sy_a), shaft_end], fill=color, width=lw)

    # Filled triangle arrowhead
    px = -ny
    py = nx
    tip = (ex, ey)
    base = (ex - nx * arrow_size, ey - ny * arrow_size)
    left = (base[0] + px * arrow_size * 0.35, base[1] + py * arrow_size * 0.35)
    right = (base[0] - px * arrow_size * 0.35, base[1] - py * arrow_size * 0.35)
    draw.polygon([tip, left, right], fill=color)


def generate_function_graphs(json_path=None, output_dir=".analysis/figures", function_list=None,
                             style="plain"):
    if function_list is not None:
        functions = function_list
    else:
        if json_path is None:
            raise ValueError("Either json_path or function_list must be provided")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        functions = data.get("functions", [])
        if not functions:
            logger.warning("No functions data found in JSON")
            return

    if not functions:
        logger.warning("No function data to generate graphs")
        return

    st = STYLES.get(style, STYLES["plain"])

    os.makedirs(output_dir, exist_ok=True)

    CENTER_FS = 12
    SIDE_FS = 12
    gap = 0.6
    DPI = 200
    SCALE = 1.5 * DPI  # pixels per data-unit

    for idx, total, func in iter_progress(functions, "Generating graphs"):
        fname = func.get("name", "unknown")
        callers = [c for c in func.get("called_by", []) if c != fname]
        callees = [c for c in func.get("calls", []) if c != fname]

        logger.debug("(%s/%s) Generating: %s", idx, total, fname)

        fname_display = _wrap_text(fname, CENTER_WRAP)
        center_height = get_box_height(CENTER_FS, lines=fname_display.count("\n") + 1,padding=0.2)
        side_height = get_box_height(SIDE_FS)

        wrapped = {fname: fname_display}
        box_widths = {}
        box_heights = {}
        box_widths[fname] = get_box_width(fname_display, min_width=1.5, padding=0, fontsize=CENTER_FS)
        box_heights[fname] = center_height
        for c in callers:
            wtext = _wrap_text(c, SIDE_WRAP)
            wrapped[c] = wtext
            box_widths[c] = get_box_width(wtext, fontsize=SIDE_FS)
            box_heights[c] = get_box_height(SIDE_FS, lines=wtext.count("\n") + 1)
        for c in callees:
            wtext = _wrap_text(c, SIDE_WRAP)
            wrapped[c] = wtext
            box_widths[c] = get_box_width(wtext, fontsize=SIDE_FS)
            box_heights[c] = get_box_height(SIDE_FS, lines=wtext.count("\n") + 1)

        pos = {}
        mid_w = box_widths[fname]
        pos[fname] = (0, 0)

        # Stack callers from top to bottom, accounting for varying heights
        caller_right_edge = -mid_w / 2 - gap
        total_caller_h = sum(box_heights.get(c, side_height) for c in callers) if callers else 0
        caller_gap = 0.18 if callers else 0
        caller_y_start = (total_caller_h + caller_gap * (len(callers) - 1)) / 2
        cy = caller_y_start
        for c in callers:
            w = box_widths[c]
            h = box_heights.get(c, side_height)
            x = caller_right_edge - w / 2
            y = cy - h / 2
            cy -= h + caller_gap
            pos[c] = (x, y)

        # Stack callees from top to bottom
        callee_left_edge = mid_w / 2 + gap
        total_callee_h = sum(box_heights.get(c, side_height) for c in callees) if callees else 0
        callee_gap = 0.18 if callees else 0
        callee_y_start = (total_callee_h + callee_gap * (len(callees) - 1)) / 2
        cy = callee_y_start
        for c in callees:
            w = box_widths[c]
            h = box_heights.get(c, side_height)
            x = callee_left_edge + w / 2
            y = cy - h / 2
            cy -= h + callee_gap
            pos[c] = (x, y)

        # Compute actual vertical extent from positions + box heights
        all_y_edges = []
        for node_name, (_, py) in pos.items():
            h = box_heights.get(node_name, side_height)
            all_y_edges.append(py - h / 2)
            all_y_edges.append(py + h / 2)

        horizontal_edges = []
        for node_name, (x, _) in pos.items():
            horizontal_edges.append(x - box_widths[node_name] / 2)
            horizontal_edges.append(x + box_widths[node_name] / 2)
        min_x = min(horizontal_edges) - 0.1
        max_x = max(horizontal_edges) + 0.1
        min_y = min(all_y_edges) - 0.1
        max_y = max(all_y_edges) + 0.1

        # --- Pixel-space rendering ---
        margin_x_d = 0.1
        margin_y_d = 0.1
        px_min_x = min_x - margin_x_d
        px_max_x = max_x + margin_x_d
        px_min_y = min_y - margin_y_d
        px_max_y = max_y + margin_y_d

        img_w = max(100, int((px_max_x - px_min_x) * SCALE))
        img_h = max(100, int((px_max_y - px_min_y) * SCALE))

        bg_rgb = _hex_to_rgb(st["background_color"])
        img = Image.new("RGB", (img_w, img_h), bg_rgb)
        draw = ImageDraw.Draw(img)

        def _to_px(*args):
            """Convert data coordinates to pixel coordinates.

            Accepts either _to_px(x, y) or _to_px((x, y)).
            """
            if len(args) == 1:
                x, y = args[0]
            else:
                x, y = args
            return (int((x - px_min_x) * SCALE), int((y - px_min_y) * SCALE))

        # Center function card
        cpx, cpy = _to_px(pos[fname])
        cpw = int(box_widths[fname] * SCALE)
        cph = int(box_heights[fname] * SCALE)
        draw_card(draw, cpx, cpy, cpw, cph, wrapped[fname],
                  _hex_to_rgb(st["center_fill"]), _hex_to_rgb(st["center_edge"]),
                  _hex_to_rgb(st["center_text"]), fontsize=CENTER_FS,
                  style=st, scale=SCALE)

        # Callers + connectors
        if callers:
            for c in callers:
                cx, cy_data = pos[c]
                pcx, pcy = _to_px(cx, cy_data)
                pcw = int(box_widths[c] * SCALE)
                pch = int(box_heights.get(c, side_height) * SCALE)
                draw_card(draw, pcx, pcy, pcw, pch, wrapped.get(c, c),
                          _hex_to_rgb(st["caller_fill"]), _hex_to_rgb(st["caller_edge"]),
                          _hex_to_rgb(st["caller_text"]), fontsize=SIDE_FS,
                          style=st, scale=SCALE)

                conn_start = _to_px(cx + box_widths[c] / 2, cy_data)
                conn_end = _to_px(-mid_w / 2 , 0)
                draw_connector(draw, conn_start, conn_end,
                               _hex_to_rgb(st["caller_line"]),
                               linewidth=st["arrow_linewidth"])

        # Callees + connectors
        if callees:
            for c in callees:
                cx, cy_data = pos[c]
                pcx, pcy = _to_px(cx, cy_data)
                pcw = int(box_widths[c] * SCALE)
                pch = int(box_heights.get(c, side_height) * SCALE)
                draw_card(draw, pcx, pcy, pcw, pch, wrapped.get(c, c),
                          _hex_to_rgb(st["callee_fill"]), _hex_to_rgb(st["callee_edge"]),
                          _hex_to_rgb(st["callee_text"]), fontsize=SIDE_FS,
                          style=st, scale=SCALE)

                conn_start = _to_px(mid_w / 2 , 0)
                conn_end = _to_px(cx - box_widths[c] / 2, cy_data)
                draw_connector(draw, conn_start, conn_end,
                               _hex_to_rgb(st["callee_line"]),
                               linewidth=st["arrow_linewidth"])

        # Save
        safe_name = fname.replace('\\', '_').replace('/', '_').replace(':', '_')
        out_path = os.path.join(output_dir, f"{safe_name}.png")
        img.info["dpi"] = (DPI, DPI)
        img.save(out_path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate function call graphs")
    parser.add_argument("--json", "-j", default=".analysis/INIT_functions.json",
                        help="Path to functions JSON file (default .analysis/INIT_functions.json)")
    parser.add_argument("--output", "-o", default=".analysis/figures",
                        help="Output directory for images (default .analysis/figures)")
    args = parser.parse_args()

    generate_function_graphs(json_path=args.json, output_dir=args.output)


if __name__ == "__main__":
    main()
