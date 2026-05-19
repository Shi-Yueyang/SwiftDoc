
"""
为 functions_with_ai.json 中的每个函数生成调用关系图。
图结构：左侧调用者（红色分支汇聚）→ 中间当前函数 → 右侧被调用者（蓝色分支分发）
"""

import json
import os
import logging
import matplotlib.pyplot as plt

from utils import iter_progress


logger = logging.getLogger(__name__)



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

        y_step = 0.6               # 节点垂直间距
        gap = 1.5                 # 中间函数与左右两侧总线的间隙
        fixed_padding = 0.3       # 矩形左右内边距
        char_width = 0.07         # 每个字符的宽度（英寸）

        def get_w(s):
            text_width = len(s) * char_width
            return text_width + fixed_padding * 2

        box_widths = {}
        box_widths[fname] = get_w(fname)
        for c in callers:
            box_widths[c] = get_w(c)
        for c in callees:
            box_widths[c] = get_w(c)

        pos = {}
        mid_w = box_widths[fname]
        pos[fname] = (0, 0)

        caller_right_edge = -mid_w/2 - gap
        for i, c in enumerate(callers):
            w = box_widths[c]
            x = caller_right_edge - w/2
            y = i * y_step - (len(callers)-1)*y_step/2
            pos[c] = (x, y)

        callee_left_edge = mid_w/2 + gap
        for i, c in enumerate(callees):
            w = box_widths[c]
            x = callee_left_edge + w/2
            y = i * y_step - (len(callees)-1)*y_step/2
            pos[c] = (x, y)

        left_bus_x = -mid_w/2 - gap/2
        right_bus_x = mid_w/2 + gap/2

        max_h = max(len(callers), len(callees), 1)
        fig, ax = plt.subplots(figsize=(12, max(3.5, max_h * 0.7)))

        for node, (x, y) in pos.items():
            w = box_widths[node]
            h = 0.35
            rect = plt.Rectangle((x - w/2, y - h/2), w, h,
                                 facecolor='white', edgecolor='black', linewidth=1.5)
            ax.add_patch(rect)
            ax.text(x, y, node, ha='center', va='center', fontsize=10)

        # -------------------------- 左侧箭头（红色：分支→总线→中间） --------------------------
        if callers:
            for c in callers:
                x0, y0 = pos[c]
                w0 = box_widths[c]
                start_x = x0 + w0/2
                ax.plot([start_x, left_bus_x], [y0, y0], color='red', lw=2)
            
            ys = [pos[c][1] for c in callers]
            y_min, y_max = min(ys), max(ys)
            ax.plot([left_bus_x, left_bus_x], [y_min, y_max], color='red', lw=2)
            
            ax.plot([left_bus_x, -mid_w/2], [0, 0], color='red', lw=2)
            ax.arrow(-mid_w/2 - 0.15, 0, 0.12, 0,
                     head_width=0.12, head_length=0.12,
                     fc='red', ec='red', length_includes_head=True)

        # -------------------------- 右侧箭头（蓝色：中间→总线→分支） --------------------------
        if callees:
            ax.plot([mid_w/2, right_bus_x], [0, 0], color='blue', lw=2)
           
            ys = [pos[c][1] for c in callees]
            y_min, y_max = min(ys), max(ys)
            ax.plot([right_bus_x, right_bus_x], [y_min, y_max], color='blue', lw=2)
            
            for c in callees:
                x1, y1 = pos[c]
                w1 = box_widths[c]
                end_x = x1 - w1/2
                ax.plot([right_bus_x, end_x], [y1, y1], color='blue', lw=2)
                ax.arrow(end_x - 0.15, y1, 0.12, 0,
                         head_width=0.12, head_length=0.12,
                         fc='blue', ec='blue', length_includes_head=True)

        ax.axis('equal')
        ax.axis('off')
        plt.tight_layout()

        safe_name = fname.replace('\\', '_').replace('/', '_').replace(':', '_')
        out_path = os.path.join(output_dir, f"{safe_name}.png")
        plt.savefig(out_path, dpi=150)
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