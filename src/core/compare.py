#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Comparison utilities for detecting added/modified/removed functions and types
between cached and freshly-extracted analysis data.
"""

import logging


logger = logging.getLogger(__name__)


# 对比函数
def compare_functions(old_funcs, new_funcs):
    """
    对比两个函数列表，返回差异字典。
    old_funcs: 上一版本的函数列表（列表，每个元素为函数字典）
    new_funcs: 当前版本的函数列表
    返回:
        {
            "added": [完整函数定义],
            "modified": [{"old": 旧版本完整函数定义, "new": 新版本完整函数定义}],
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


# 对比类型
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
            old_core = {k: v for k, v in old_def.items() if k != 'type_description'}
            new_core = {k: v for k, v in new_def.items() if k != 'type_description'}
            if old_core != new_core:
                # 提供新旧定义的简要预览
                modified[name] = new_def
                modified[name]['_old_preview'] = str(old_core)[:200]
    return {"added": added, "modified": modified, "removed": removed}
