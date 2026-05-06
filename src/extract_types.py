"""
Extract type definitions (structs, unions, enums, typedefs) from all .h files in the specified folder, 
exclude commented-out types, associate the preceding comments, and output a JSON file with the numbering format A_1, A_2, ...
"""

import os
import re
import json
import time
import argparse
from utils import decode_file
from ai_utils import ai_prompt_for_type, call_ai


def collect_type_definitions_with_comments(header_text):
    """
    Extract valid type definitions (not inside comments) and associate preceding comments.
    Supported patterns:
    typedef enum [tag] { ... } Name;
    typedef struct [tag] { ... } Name;
    typedef union [tag] { ... } Name;
    typedef Type Alias; (Simple type)
    typedef Type Alias[Size]; (Array type)
    Type names must start with an uppercase or lowercase letter.

    """
    comment_spans = []
    for match in re.finditer(r'/\*.*?\*/', header_text, re.DOTALL):
        comment_spans.append((match.start(), match.end(), match.group(0)))
    for match in re.finditer(r'//.*?(?=\n|$)', header_text):
        comment_spans.append((match.start(), match.end(), match.group(0)))
    comment_spans.sort(key=lambda x: x[0])

    def is_in_comment(pos):
        for cs, ce, _ in comment_spans:
            if cs <= pos < ce:
                return True
        return False

    type_defs = {}
    matches = [] 

    patterns = [
        # 1. typedef enum [tag] { ... } Name;
        (r'typedef\s+enum\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;', 'enum'),
        # 2. typedef struct [tag] { ... } Name;
        (r'typedef\s+struct\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;', 'struct'),
        # 3. typedef union [tag] { ... } Name;
        (r'typedef\s+union\s+(?:\w+\s+)?\{([^}]*)\}\s*([A-Za-z][A-Za-z0-9_]*)\s*;', 'union'),
        # 4. 数组 typedef，如 typedef BYTE_8 DEVICE_ID[3];
        (r'typedef\s+([^;]+?)\s+([A-Za-z][A-Za-z0-9_]*)\s*\[([^\]]*)\]\s*;', 'array'),
        # 5. 普通 typedef（排除包含 struct/enum/union 的，避免误匹配）
        (r'typedef\s+(?!struct|enum|union)([^;]+?)\s+([A-Za-z][A-Za-z0-9_]*)\s*;', 'typedef')
    ]

    for pattern, kind in patterns:
        for match in re.finditer(pattern, header_text, re.DOTALL):
            start, end = match.start(), match.end()
            if is_in_comment(start):
                continue
            if kind == 'enum':
                body, name = match.groups()
                values = [v.strip() for v in body.replace('\n', ' ').split(',') if v.strip()]
                definition = {"kind": "enum", "name": name, "values": values}
            elif kind in ('struct', 'union'):
                body, name = match.groups()
                members = [m.strip() + ';' for m in body.split(';') if m.strip()]
                definition = {"kind": kind, "name": name, "members": members}
            elif kind == 'array':
                orig, name, array_size = match.groups()
                definition = {"kind": "typedef", "name": name, "original_type": orig.strip() + f"[{array_size}]"}
            else:  # typedef
                orig, name = match.groups()
                definition = {"kind": "typedef", "name": name, "original_type": orig.strip()}
            matches.append((start, end, name, definition))

    matches.sort(key=lambda x: x[0])
    comment_spans.sort(key=lambda x: x[1])

    for start, end, name, definition in matches:
        best_comment = None
        best_end = -1
        for c_start, c_end, c_text in comment_spans:
            if c_end <= start and c_end > best_end:
                best_end = c_end
                best_comment = c_text
        if best_comment:
            if best_comment.startswith('/*') and best_comment.endswith('*/'):
                cleaned = best_comment[2:-2].strip()
            elif best_comment.startswith('//'):
                cleaned = best_comment[2:].strip()
            else:
                cleaned = best_comment.strip()
            lines = cleaned.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.lstrip('*').strip()
                cleaned_lines.append(line)
            cleaned = '\n'.join(cleaned_lines)
            definition['comment'] = cleaned
        else:
            definition['comment'] = None
        type_defs[name] = definition

    return type_defs

def collect_all_types_from_project(project_dir, output_dir=".analysis", enable_ai=True):
    """
    Extract type definitions from all .h files in the project directory, associate comments, and save to JSON.
    """
    h_files = []
    for root, dirs, files in os.walk(project_dir):
        for f in files:
            if f.endswith('.h'):
                h_files.append(os.path.join(root, f))

    all_types = {}
    for hf in h_files:
        with open(hf, 'rb') as f:
            raw = f.read()
        text = decode_file(raw) 
        all_types.update(collect_type_definitions_with_comments(text))

    unique_types = {}
    for name, defn in all_types.items():
        if name not in unique_types:
            unique_types[name] = defn
        else:
            print(f"Warning: duplicate type definition '{name}' ignored")

    sorted_names = sorted(unique_types.keys())
    type_refs = {name: f"A_{idx+1}" for idx, name in enumerate(sorted_names)}

    if enable_ai:
        for idx, (type_name, defn) in enumerate(unique_types.items(), 1):
            prompt = ai_prompt_for_type(type_name, defn)
            description = call_ai(prompt, max_tokens=300)
            if description:
                defn['type_description'] = description
            else:
                defn['type_description'] = "AI 分析失败"
            time.sleep(0.5) 
            
    output_data = {
        "description": "Type definitions extracted from project header files (excluding commented-out ones).",
        "type_definitions": unique_types,
        "type_references": type_refs
    }

    os.makedirs(output_dir, exist_ok=True)
    folder_name = os.path.basename(os.path.normpath(project_dir))
    output_file = os.path.join(output_dir, f"{folder_name}_global_types.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"Type definitions saved to {output_file}")
    print(f"Total types found: {len(unique_types)}")
    return output_file

def main():
    parser = argparse.ArgumentParser(description="Extract type definitions from C/C++ header files.")
    parser.add_argument("project_dir", nargs='?', default="ATP_CODE/INIT", help="Root directory of the project (contains .c and .h files)")
    parser.add_argument("--output", "-o", default=".analysis", help="Output directory (default: .analysis)")
    parser.add_argument("--outfile", "-f", default="INIT_global_types.json", help="Output JSON filename (default: global_types.json)")
    args = parser.parse_args()

    collect_all_types_from_project(args.project_dir, args.output)

if __name__ == "__main__":
    main()