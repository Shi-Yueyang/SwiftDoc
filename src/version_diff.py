#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Version management and diff utilities for function analysis.
"""

import os
import json
import copy
import time
import logging
from ai_utils import ai_prompt_for_type, ai_prompt_for_function, call_ai


logger = logging.getLogger(__name__)


def generate_versioned_filename(filepath):
    """
    如果文件已存在，生成带版本号的新文件名。
    例如: /path/to/ATP_CODE_functions.json -> /path/to/ATP_CODE_functions_v1.json
    如果 v1 也存在，则 v2，依此类推。
    返回: 新文件路径（字符串）
    """
    if not os.path.exists(filepath):
        return filepath
    base, ext = os.path.splitext(filepath)
    version = 1
    while True:
        new_path = f"{base}_v{version}{ext}"
        if not os.path.exists(new_path):
            return new_path
        version += 1

#对比函数
def compare_functions(old_funcs, new_funcs):
    """
    对比两个函数列表，返回差异字典。
    old_funcs: 上一版本的函数列表（列表，每个元素为函数字典）
    new_funcs: 当前版本的函数列表
    返回:
        {
            "added": [完整函数定义],   # 列表，每个元素是函数的完整 dict
            "modified": [
                {
                    "old": 旧版本完整函数定义,
                    "new": 新版本完整函数定义
                }
            ],
            "removed": [完整函数定义]
        }
    """
    old_dict = {f["name"]: f for f in old_funcs}
    new_dict = {f["name"]: f for f in new_funcs}

    added = []
    modified = []
    removed = []

    all_names = set(old_dict.keys()) | set(new_dict.keys())
    for name in all_names:
        old_func = old_dict.get(name)
        new_func = new_dict.get(name)
        if old_func is None:
            added.append(new_func)
        elif new_func is None:
            removed.append(old_func)
        else:
            old_body = old_func.get("normalized_body", "")
            new_body = new_func.get("normalized_body", "")
            if old_body != new_body:
                modified.append({
                    "old": old_func,
                    "new": new_func
                })
    return {"added": added, "modified": modified, "removed": removed}
#加载以前的函数
def load_previous_functions(filepath):
    """
    从文件加载上一版本的函数列表。
    如果文件不存在或格式错误，返回空列表。
    """
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("functions", [])
    except (json.JSONDecodeError, IOError):
        return []
#更新函数
# version_diff.py

import os
import json
import time
from ai_utils import ai_prompt_for_function, call_ai

def update_master_from_diff_functions(master_json_path, diff_json_path, target_dir=None, enable_ai=True):
    """
    根据 functions_diff.json 增量更新主函数 JSON 文件。

    参数：
        master_json_path: 主文件路径（如 .analysis/ATP_CODE_functions.json）
        diff_json_path:   functions_diff.json 路径
        target_dir:       可选，只处理该目录下的变化函数（若为 None 则处理所有）
        enable_ai:        是否对新增/修改的函数调用 AI 生成描述
    """
    if not os.path.exists(diff_json_path):
        logger.warning("差异文件不存在: %s", diff_json_path)
        return False

    with open(diff_json_path, 'r', encoding='utf-8') as f:
        diff = json.load(f)

    added = diff.get("added", [])          
    modified = diff.get("modified", [])   
    removed = diff.get("removed", [])     

    if not (added or modified or removed):
        logger.info("没有需要更新的函数变化。")
        return False

    # 过滤函数（根据 target_dir）
    def is_in_target(func_def):
        if target_dir is None:
            return True
        func_file = os.path.normpath(func_def.get("file", ""))
        target_norm = os.path.normpath(target_dir)
        return func_file.startswith(target_norm)

    filtered_added = [f for f in added if is_in_target(f)]
    filtered_modified = [m["new"] for m in modified if is_in_target(m["new"])]
    filtered_removed = [f for f in removed if is_in_target(f)]

    if not (filtered_added or filtered_modified or filtered_removed):
        logger.info("没有与目标目录相关的函数变化 (target_dir=%s)", target_dir)
        return False

    # 加载主文件
    if os.path.exists(master_json_path):
        with open(master_json_path, 'r', encoding='utf-8') as f:
            master_data = json.load(f)
        master_funcs = master_data.get("functions", [])
    else:
        master_funcs = []

    func_dict = {f["name"]: f for f in master_funcs}

    # 需要 AI 的函数
    changed_funcs = filtered_added + filtered_modified
    if enable_ai:
        logger.info("正在为 %s 个变化函数生成 AI 描述...", len(changed_funcs))
        for func_def in changed_funcs:
            if isinstance(func_def.get('returns'), list) and func_def['returns'] and isinstance(func_def['returns'][0], str):
                func_def['returns'] = [{"expression": expr, "return_description": ""} for expr in func_def['returns']]
            else:
                for ret in func_def.get('returns', []):
                    if isinstance(ret, dict):
                        ret.setdefault('return_description', '')
            for inp in func_def.get('inputs', []):
                inp.setdefault('inputs_description', '')

            prompt = ai_prompt_for_function(func_def)
            response = call_ai(prompt, temperature=1.0, max_tokens=800, retry_count=1)
            if response:
                try:
                    desc = json.loads(response)
                    func_def['algorithm_logic'] = desc.get('algorithm_logic', '')
                    param_descs = {item['name']: item.get('inputs_description', '') for item in desc.get('inputs_description', [])}
                    for inp in func_def.get('inputs', []):
                        inp['inputs_description'] = param_descs.get(inp['name'], inp.get('inputs_description', ''))
                    return_descs = desc.get('return_values', [])
                    for idx, ret_item in enumerate(func_def.get('returns', [])):
                        if idx < len(return_descs):
                            ret_item['return_description'] = return_descs[idx]
                        else:
                            ret_item.setdefault('return_description', '')
                except json.JSONDecodeError:
                    func_def['algorithm_logic'] = "AI 分析失败"
            else:
                func_def['algorithm_logic'] = "AI 分析失败"
            time.sleep(0.5)
        logger.info("完成 %s 个函数的 AI 增强", len(changed_funcs))
    else:
        for func_def in changed_funcs:
            func_def.setdefault('algorithm_logic', '')
            for inp in func_def.get('inputs', []):
                inp.setdefault('inputs_description', '')
            for ret in func_def.get('returns', []):
                ret.setdefault('return_description', '')

    # 更新或添加
    for func_def in changed_funcs:
        func_dict[func_def["name"]] = func_def

    # 删除
    for func_def in filtered_removed:
        func_dict.pop(func_def["name"], None)

    # 保存主文件
    updated_funcs = list(func_dict.values())
    master_data["functions"] = updated_funcs
    with open(master_json_path, 'w', encoding='utf-8') as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    logger.info("主函数文件更新: %s", master_json_path)
    logger.info("新增/修改: %s 个函数", len(changed_funcs))
    logger.info("删除: %s 个函数", len(filtered_removed))
    return True

#对比类型
def compare_types(old_types, new_types):
    added = {}
    modified = {}
    removed = {}
    all_names = set(old_types.keys()) | set(new_types.keys())
    for name in all_names:
        old_def = old_types.get(name)
        new_def = new_types.get(name)
        if old_def is None:
            added[name] = new_def
        elif new_def is None:
            removed[name] = old_def
        else:
            # 比较核心定义（忽略 type_description）
            old_core = {k:v for k,v in old_def.items() if k != 'type_description'}
            new_core = {k:v for k,v in new_def.items() if k != 'type_description'}
            if old_core != new_core:
                # 提供新旧定义的简要预览（可以取 full 定义或关键字段）
                modified[name] = new_def
                modified[name]['_old_preview'] = str(old_core)[:200]
    return {"added": added, "modified": modified, "removed": removed}  
#更新类型
def update_master_from_diff(master_json_path, diff_json_path, enable_ai=True):
    """
    根据 types_diff.json 更新主类型 JSON 文件。

    参数：
        master_json_path: 主文件路径（如 .analysis/ATP_CODE_global_types.json）
        diff_json_path:   types_diff.json 路径
        enable_ai:        是否对新增/修改的类型调用 AI 生成描述
    """

    # 1. 加载 diff
    if not os.path.exists(diff_json_path):
        logger.warning("差异文件不存在: %s", diff_json_path)
        return
    with open(diff_json_path, 'r', encoding='utf-8') as f:
        diff = json.load(f)

    added = diff.get("added", {})
    modified = diff.get("modified", {})
    removed = diff.get("removed", {})

    if not (added or modified or removed):
        logger.info("没有需要更新的类型变化。")
        return

    # 2. 加载主文件（如果不存在则创建空结构）
    if os.path.exists(master_json_path):
        with open(master_json_path, 'r', encoding='utf-8') as f:
            master_data = json.load(f)
        master_types = master_data.get("type_definitions", {})
        master_refs = master_data.get("type_references", {})
    else:
        master_types = {}
        master_refs = {}

    # 3. 处理新增和修改（从 diff 中获取完整定义）
    changed_names = set(added.keys()) | set(modified.keys())
    for type_name in changed_names:
        # 合并：优先使用 modified，若不存在则使用 added
        new_def = modified.get(type_name) or added.get(type_name)
        if not new_def:
            continue
        new_def = copy.deepcopy(new_def)
        
        # 如果需要 AI 描述，生成
        if enable_ai:
            prompt = ai_prompt_for_type(type_name, new_def)
            desc = call_ai(prompt, temperature=1.0, max_tokens=800, retry_count=1)
            new_def['type_description'] = desc if desc else "AI 分析失败"
            time.sleep(0.5)
        else:
            # 保留主文件中已有的描述（如果有）
            if type_name in master_types and 'type_description' in master_types[type_name]:
                new_def['type_description'] = master_types[type_name]['type_description']
            else:
                new_def.setdefault('type_description', "")
        master_types[type_name] = new_def

    # 4. 处理删除
    for type_name in removed.keys():
        if type_name in master_types:
            del master_types[type_name]
            logger.info("Removed type: %s", type_name)

    # 5. 重新生成 type_references（保持字母排序）
    sorted_names = sorted(master_types.keys())
    master_refs = {name: f"A_{idx+1}" for idx, name in enumerate(sorted_names)}

    # 6. 保存主文件
    master_data.update({
        "type_definitions": master_types,
        "type_references": master_refs
    })
    with open(master_json_path, 'w', encoding='utf-8') as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    logger.info("Master types JSON updated: %s", master_json_path)
    logger.info("Added/Modified: %s types", len(changed_names))
    logger.info("Removed: %s types", len(removed))