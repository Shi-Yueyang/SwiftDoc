"""
Generate call-graph diagrams for each function.
Layout: callers (left) → current function (center) → callees (right).
"""

import json
import os
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from core.utils import iter_progress


logger = logging.getLogger(__name__)

BACKGROUND_COLOR = "#f3f6fb"
PANEL_COLOR = "#e8eef9"
CURRENT_FILL = "#111827"
CURRENT_EDGE = "#1f2937"
CURRENT_TEXT = "#f8fafc"
CALLER_FILL = "#fff1f2"
CALLER_EDGE = "#fb7185"
CALLER_LINE = "#e11d48"
CALLEE_FILL = "#eff6ff"
CALLEE_EDGE = "#60a5fa"
CALLEE_LINE = "#2563eb"
LABEL_COLOR = "#64748b"
CARD_SHADOW = (0, -3)

MAX_NAME_LEN = 34


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


def get_box_width(text, char_width=0.11, min_width=3.0, padding=0.95, fontsize=11):
    scale = fontsize / 11.0
    return max(min_width * scale, estimate_text_units(text) * char_width * scale + padding * scale)


def get_box_height(fontsize):
    return fontsize * 0.072


def draw_card(ax, x, y, width, height, text, fill, edge, text_color, fontsize=11):
    shadow = FancyBboxPatch(
        (x - width / 2 + 0.07, y - height / 2 - 0.07),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.18",
        linewidth=0,
        facecolor="#0f172a",
        alpha=0.08,
        zorder=1,
    )
    ax.add_patch(shadow)

    card = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.18",
        linewidth=1.8,
        edgecolor=edge,
        facecolor=fill,
        zorder=3,
    )
    card.set_path_effects([
        path_effects.withSimplePatchShadow(offset=CARD_SHADOW, alpha=0.10),
        path_effects.Normal(),
    ])
    ax.add_patch(card)
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=text_color,
        fontweight="semibold",
        zorder=4,
    )


def draw_connector(ax, start, end, color):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=18,
        linewidth=2.8,
        color=color,
        connectionstyle="arc3,rad=0.0",
        capstyle="round",
        joinstyle="round",
        zorder=2,
    )
    ax.add_patch(arrow)


def draw_section_label(ax, x, y, text):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=10,
        color=LABEL_COLOR,
        fontweight="bold",
        zorder=5,
    )


def _truncated(text):
    if len(text) > MAX_NAME_LEN:
        return text[:MAX_NAME_LEN - 1] + "…"
    return text


def generate_function_graphs(json_path=None, output_dir=".analysis/figures", function_list=None):
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

    os.makedirs(output_dir, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'font.family': 'sans-serif'})
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    CENTER_FS = 16
    SIDE_FS = 13
    gap = 2.5
    y_step = 1.2

    for idx, total, func in iter_progress(functions, "Generating graphs"):
        fname = func.get("name", "unknown")
        callers = func.get("called_by", [])
        callees = func.get("calls", [])

        logger.debug("(%s/%s) Generating: %s", idx, total, fname)

        fname_display = _truncated(fname)
        center_height = get_box_height(CENTER_FS)
        side_height = get_box_height(SIDE_FS)

        box_widths = {}
        box_widths[fname] = get_box_width(fname_display, min_width=4.2, padding=1.3, fontsize=CENTER_FS)
        for c in callers:
            box_widths[c] = get_box_width(_truncated(c), fontsize=SIDE_FS)
        for c in callees:
            box_widths[c] = get_box_width(_truncated(c), fontsize=SIDE_FS)

        pos = {}
        mid_w = box_widths[fname]
        pos[fname] = (0, 0)

        caller_right_edge = -mid_w / 2 - gap
        for i, c in enumerate(callers):
            w = box_widths[c]
            x = caller_right_edge - w / 2
            y = i * y_step - (len(callers) - 1) * y_step / 2
            pos[c] = (x, y)

        callee_left_edge = mid_w / 2 + gap
        for i, c in enumerate(callees):
            w = box_widths[c]
            x = callee_left_edge + w / 2
            y = i * y_step - (len(callees) - 1) * y_step / 2
            pos[c] = (x, y)

        max_h = max(len(callers), len(callees), 1)
        fig, ax = plt.subplots(figsize=(14, max(5.0, max_h * 1.25)))
        fig.patch.set_facecolor(BACKGROUND_COLOR)
        ax.set_facecolor(BACKGROUND_COLOR)

        horizontal_edges = []
        for node_name, (x, _) in pos.items():
            horizontal_edges.append(x - box_widths[node_name] / 2)
            horizontal_edges.append(x + box_widths[node_name] / 2)
        y_values = [y for _, y in pos.values()] or [0]
        min_x = min(horizontal_edges) - 1.6
        max_x = max(horizontal_edges) + 1.6
        min_y = min(y_values) - 1.8
        max_y = max(y_values) + 2.0

        panel = FancyBboxPatch(
            (min_x + 0.2, min_y + 0.2),
            max_x - min_x - 0.4,
            max_y - min_y - 0.4,
            boxstyle="round,pad=0.02,rounding_size=0.25",
            linewidth=0,
            facecolor=PANEL_COLOR,
            alpha=0.55,
            zorder=0,
        )
        ax.add_patch(panel)

        draw_card(
            ax, pos[fname][0], pos[fname][1],
            box_widths[fname], center_height, fname_display,
            CURRENT_FILL, CURRENT_EDGE, CURRENT_TEXT,
            fontsize=CENTER_FS,
        )

        if callers:
            draw_section_label(
                ax,
                min(pos[c][0] for c in callers),
                max_y - 0.65,
                "CALLERS",
            )
            for c in callers:
                x0, y0 = pos[c]
                draw_card(
                    ax, x0, y0,
                    box_widths[c], side_height, _truncated(c),
                    CALLER_FILL, CALLER_EDGE, "#881337",
                    fontsize=SIDE_FS,
                )
                draw_connector(
                    ax,
                    (x0 + box_widths[c] / 2, y0),
                    (-mid_w / 2 - 0.18, 0),
                    CALLER_LINE,
                )

        if callees:
            draw_section_label(
                ax,
                max(pos[c][0] for c in callees),
                max_y - 0.65,
                "CALLS",
            )
            for c in callees:
                x1, y1 = pos[c]
                draw_card(
                    ax, x1, y1,
                    box_widths[c], side_height, _truncated(c),
                    CALLEE_FILL, CALLEE_EDGE, "#1e3a8a",
                    fontsize=SIDE_FS,
                )
                draw_connector(
                    ax,
                    (mid_w / 2 + 0.18, 0),
                    (x1 - box_widths[c] / 2, y1),
                    CALLEE_LINE,
                )

        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)
        ax.axis('off')
        plt.tight_layout()

        safe_name = fname.replace('\\', '_').replace('/', '_').replace(':', '_')
        out_path = os.path.join(output_dir, f"{safe_name}.png")
        plt.savefig(out_path, dpi=180, facecolor=fig.get_facecolor(), bbox_inches='tight')
        plt.close()


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
