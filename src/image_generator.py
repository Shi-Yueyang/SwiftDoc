
"""
为 functions_with_ai.json 中的每个函数生成调用关系图。
图结构：左侧调用者（红色分支汇聚）→ 中间当前函数 → 右侧被调用者（蓝色分支分发）
"""

import json
import os
import logging
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from utils import iter_progress


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


def get_box_width(text, char_width=0.11, min_width=3.0, padding=0.95):
    return max(min_width, estimate_text_units(text) * char_width + padding)


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
        fontsize=9,
        color=LABEL_COLOR,
        fontweight="bold",
        zorder=5,
    )



def generate_function_graphs(json_path=None, output_dir=".analysis/figures", function_list=None):
    """
    生成函数调用关系图。

    参数:
        json_path: JSON 文件路径（当 function_list 为 None 时必填）
        output_dir: 输出图片目录
        function_list: 可选，函数列表（每个函数应包含 name, called_by, calls 字段）
    """
    # 获取函数列表
    if function_list is not None:
        functions = function_list
    else:
        if json_path is None:
            raise ValueError("Either json_path or function_list must be provided")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        functions = data.get("functions", [])
        if not functions:
            logger.warning("JSON 中没有找到 functions 数据")
            return

    if not functions:
        logger.warning("没有函数数据可生成图表")
        return

    os.makedirs(output_dir, exist_ok=True)
    plt.rcParams.update({'font.size': 10, 'font.family': 'sans-serif'})
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']  # 支持中文
    plt.rcParams['axes.unicode_minus'] = False

    for idx, total, func in iter_progress(functions, "Generating graphs"):
        fname = func.get("name", "unknown")
        callers = func.get("called_by", [])
        callees = func.get("calls", [])

        logger.debug("(%s/%s) 生成: %s", idx, total, fname)

        y_step = 1.0
        gap = 2.0
        box_height = 0.72

        box_widths = {}
        box_widths[fname] = get_box_width(fname, min_width=4.2, padding=1.3)
        for c in callers:
            box_widths[c] = get_box_width(c)
        for c in callees:
            box_widths[c] = get_box_width(c)

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
        fig, ax = plt.subplots(figsize=(13, max(4.4, max_h * 1.05)))
        fig.patch.set_facecolor(BACKGROUND_COLOR)
        ax.set_facecolor(BACKGROUND_COLOR)

        x_values = [x for x, _ in pos.values()]
        y_values = [y for _, y in pos.values()] or [0]
        horizontal_edges = []
        for node_name, (x, _) in pos.items():
            horizontal_edges.append(x - box_widths[node_name] / 2)
            horizontal_edges.append(x + box_widths[node_name] / 2)
        min_x = min(horizontal_edges) - 1.4
        max_x = max(horizontal_edges) + 1.4
        min_y = min(y_values) - 1.6
        max_y = max(y_values) + 1.8

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
            ax,
            pos[fname][0],
            pos[fname][1],
            box_widths[fname],
            box_height,
            fname,
            CURRENT_FILL,
            CURRENT_EDGE,
            CURRENT_TEXT,
            fontsize=12,
        )

        if callers:
            draw_section_label(
                ax,
                min(pos[c][0] for c in callers),
                max_y - 0.55,
                "CALLERS",
            )
            for c in callers:
                x0, y0 = pos[c]
                draw_card(
                    ax,
                    x0,
                    y0,
                    box_widths[c],
                    box_height,
                    c,
                    CALLER_FILL,
                    CALLER_EDGE,
                    "#881337",
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
                max_y - 0.55,
                "CALLS",
            )
            for c in callees:
                x1, y1 = pos[c]
                draw_card(
                    ax,
                    x1,
                    y1,
                    box_widths[c],
                    box_height,
                    c,
                    CALLEE_FILL,
                    CALLEE_EDGE,
                    "#1e3a8a",
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
    parser = argparse.ArgumentParser(description="生成函数调用关系图")
    parser.add_argument("--json", "-j", default=".analysis/INIT_functions.json",
                        help="functions.json 文件路径（默认 .analysis/INIT_functions.json）")
    parser.add_argument("--output", "-o", default=".analysis/figures",
                        help="输出图片目录（默认 .analysis/figures）")
    args = parser.parse_args()

    generate_function_graphs(json_path=args.json, output_dir=args.output)


if __name__ == "__main__":
    main()