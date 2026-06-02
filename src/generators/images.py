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

STYLES = {
    "modern": {
        "background_color": "#f3f6fb",
        "panel_color": "#e8eef9",
        "center_fill": "#111827",
        "center_edge": "#1f2937",
        "center_text": "#f8fafc",
        "caller_fill": "#fff1f2",
        "caller_edge": "#fb7185",
        "caller_text": "#881337",
        "caller_line": "#e11d48",
        "callee_fill": "#eff6ff",
        "callee_edge": "#60a5fa",
        "callee_text": "#1e3a8a",
        "callee_line": "#2563eb",
        "card_shadow": (0, -3),
        "use_shadow": True,
        "rounding_size": 0.18,
        "panel_rounding_size": 0.25,
        "card_linewidth": 1.8,
        "arrow_linewidth": 2.8,
        "shadow_alpha": 0.08,
        "path_shadow_alpha": 0.10,
    },
    "plain": {
        "background_color": "#ffffff",
        "panel_color": "#ffffff",
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
        "card_shadow": (0, -3),
        "use_shadow": False,
        "rounding_size": 0.0,
        "panel_rounding_size": 0.0,
        "card_linewidth": 1.0,
        "arrow_linewidth": 1.0,
        "shadow_alpha": 0.0,
        "path_shadow_alpha": 0.0,
    },
}

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


def get_box_width(text, char_width=0.12, min_width=2.0, padding=0.0, fontsize=11):
    scale = fontsize / 11.0
    return max(min_width * scale, estimate_text_units(text) * char_width * scale)


def get_box_height(fontsize):
    return fontsize * 0.024


def draw_card(ax, x, y, width, height, text, fill, edge, text_color, fontsize=11,
              style=None):
    """Draw a single function card.

    Args:
        style: The style dict from STYLES (controls shadow, rounding, linewidth).
    """
    if style is None:
        style = STYLES["plain"]

    if style["use_shadow"]:
        shadow = FancyBboxPatch(
            (x - width / 2 + 0.07, y - height / 2 - 0.07),
            width,
            height,
            boxstyle=f"round,pad=0.02,rounding_size={style['rounding_size']}",
            linewidth=0,
            facecolor="#0f172a",
            alpha=style["shadow_alpha"],
            zorder=1,
        )
        ax.add_patch(shadow)

    card = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle=f"round,pad=0.02,rounding_size={style['rounding_size']}",
        linewidth=style["card_linewidth"],
        edgecolor=edge,
        facecolor=fill,
        zorder=3,
    )
    if style["use_shadow"]:
        card.set_path_effects([
            path_effects.withSimplePatchShadow(offset=style["card_shadow"], alpha=style["path_shadow_alpha"]),
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


def draw_connector(ax, start, end, color, linewidth=2.8):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=18,
        linewidth=linewidth,
        color=color,
        connectionstyle="arc3,rad=0.0",
        capstyle="round",
        joinstyle="round",
        zorder=2,
    )
    ax.add_patch(arrow)



def _truncated(text):
    if len(text) > MAX_NAME_LEN:
        return text[:MAX_NAME_LEN - 1] + "…"
    return text


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

    st = STYLES.get(style, STYLES["modern"])

    os.makedirs(output_dir, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'font.family': 'sans-serif'})
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    CENTER_FS = 16
    SIDE_FS = 13
    gap = 0.6
    y_step = 0.42

    for idx, total, func in iter_progress(functions, "Generating graphs"):
        fname = func.get("name", "unknown")
        callers = func.get("called_by", [])
        callees = func.get("calls", [])

        logger.debug("(%s/%s) Generating: %s", idx, total, fname)

        fname_display = _truncated(fname)
        center_height = get_box_height(CENTER_FS)
        side_height = get_box_height(SIDE_FS)

        box_widths = {}
        box_widths[fname] = get_box_width(fname_display, min_width=2.8, padding=0.0, fontsize=CENTER_FS)
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
        fig.patch.set_facecolor(st["background_color"])
        ax.set_facecolor(st["background_color"])

        horizontal_edges = []
        for node_name, (x, _) in pos.items():
            horizontal_edges.append(x - box_widths[node_name] / 2)
            horizontal_edges.append(x + box_widths[node_name] / 2)
        y_values = [y for _, y in pos.values()] or [0]
        min_x = min(horizontal_edges) - 0.6
        max_x = max(horizontal_edges) + 0.6
        min_y = min(y_values) - 0.5
        max_y = max(y_values) + 0.5

        panel = FancyBboxPatch(
            (min_x + 0.15, min_y + 0.15),
            max_x - min_x - 0.3,
            max_y - min_y - 0.3,
            boxstyle=f"round,pad=0.02,rounding_size={st['panel_rounding_size']}",
            linewidth=0,
            facecolor=st["panel_color"],
            alpha=0.55,
            zorder=0,
        )
        ax.add_patch(panel)

        draw_card(
            ax, pos[fname][0], pos[fname][1],
            box_widths[fname], center_height, fname_display,
            st["center_fill"], st["center_edge"], st["center_text"],
            fontsize=CENTER_FS, style=st,
        )

        if callers:
            for c in callers:
                x0, y0 = pos[c]
                draw_card(
                    ax, x0, y0,
                    box_widths[c], side_height, _truncated(c),
                    st["caller_fill"], st["caller_edge"], st["caller_text"],
                    fontsize=SIDE_FS, style=st,
                )
                draw_connector(
                    ax,
                    (x0 + box_widths[c] / 2, y0),
                    (-mid_w / 2 - 0.18, 0),
                    st["caller_line"],
                    linewidth=st["arrow_linewidth"],
                )

        if callees:
            for c in callees:
                x1, y1 = pos[c]
                draw_card(
                    ax, x1, y1,
                    box_widths[c], side_height, _truncated(c),
                    st["callee_fill"], st["callee_edge"], st["callee_text"],
                    fontsize=SIDE_FS, style=st,
                )
                draw_connector(
                    ax,
                    (mid_w / 2 + 0.18, 0),
                    (x1 - box_widths[c] / 2, y1),
                    st["callee_line"],
                    linewidth=st["arrow_linewidth"],
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
