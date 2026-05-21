import os
import time
import logging
from textwrap import dedent
from openai import OpenAI

from config_manager import get_missing_ai_keys, resolve_ai_config


logger = logging.getLogger(__name__)

def _get_client():
    config, details = resolve_ai_config()
    missing_keys = get_missing_ai_keys(config)
    if missing_keys:
        missing_labels = ", ".join(missing_keys)
        raise RuntimeError(
            "AI configuration is incomplete. "
            f"Missing: {missing_labels}. Checked {details['source_summary']}"
        )
    client = OpenAI(base_url=config["base_url"], api_key=config["api_key"])
    return client, config["model_name"]


def ai_prompt_for_type(type_name, definition):
    kind = definition.get("kind", "unknown")
    if kind == "struct":
        members = definition.get("members", [])
        members_str = "\n".join(members) if members else "无成员"
        prompt = dedent(
            f"""
            你是一个嵌入式C代码分析专家。请用简洁的中文描述以下结构体的用途和含义。
            结构体名：{type_name}
            成员列表：
            {members_str}
            请直接输出一段描述文字，不要加任何前缀。
            """
        ).strip()
    elif kind == "union":
        members = definition.get("members", [])
        members_str = "\n".join(members) if members else "无成员"
        prompt = dedent(
            f"""
            描述以下联合体的用途和含义（用中文）。
            联合体名：{type_name}
            成员列表：
            {members_str}
            请直接输出一段描述文字（不超过200字）。
            """
        ).strip()
    elif kind == "enum":
        values = definition.get("values", [])
        values_str = ", ".join(values) if values else "无枚举值"
        prompt = dedent(
            f"""
            描述以下枚举类型的用途和含义（用中文）
            枚举名：{type_name}
            枚举值：{values_str}
            请直接输出一段描述文字（不超过200字）。
            """
        ).strip()
    else:  # typedef
        original_type = definition.get("original_type", "")
        prompt = dedent(
            f"""
            描述以下类型别名的用途和含义（用中文）。
            别名：{type_name}
            原始类型：{original_type}
            请直接输出一段描述文字（不超过150字）。
            """
        ).strip()
    return prompt


def ai_prompt_for_function(func):
    inputs_info = []
    for inp in func['inputs']:
        inputs_info.append(f"- {inp['name']} (类型: {inp['type']}, 类别: {inp['kind']})")
    inputs_info_str = "\n".join(inputs_info)
    returns_info = "\n".join([f"- {expr}" for expr in func['returns']]) if func['returns'] else "无返回值"

    prompt = dedent(
            f"""
            你是一个嵌入式C代码分析专家。请分析以下函数，并用简洁的中文给出：

            1. 算法/逻辑描述：说明函数实现了什么算法或逻辑，不要重复代码内容。（不超过100字）
            2. 每个输入项的作用（包括形参和全局变量）。请说明在该函数中的作用以及其含义，**每个输入项的描述控制在30字以内**。
            3. 每个返回值表达式的作用（如果函数有返回值），**每个返回值的描述控制在30字以内**。

            函数名：{func['name']}
            输入项列表（形参和全局变量，已标明类别）：
            {inputs_info_str}
            返回值表达式列表：
            {returns_info}

            函数体代码：
            {func['body_code'][:1500]}

            请严格按照以下 JSON 格式输出（不要输出任何其他内容）：
            {{
                "algorithm_logic": "算法描述（100字内）",
                "inputs_description": [
                    {{"name": "输入项名称1", "inputs_description": "30字内描述"}},
                    ...
                ],
                "return_values": [
                    "返回值1的含义",
                    "返回值2的含义"
                ]
            }}
            """
        ).strip()
    return prompt


def call_ai(prompt, temperature, max_tokens, retry_count):
    logger.debug("[AI API] Call started (retries_left=%d)", retry_count)
    
    try:
        client, model_name = _get_client()
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        if not response.choices or not response.choices[0].message:
            logger.debug("[AI API] Invalid response, retrying (retries_left=%d)", retry_count - 1)
            if retry_count > 0:
                time.sleep(2)
                return call_ai(prompt, temperature, max_tokens, retry_count - 1)
            return None
        
        content = response.choices[0].message.content
        if content is None:
            content = ""
        else:
            content = content.strip()

        if len(content) == 0:
            logger.debug("[AI API] Empty response, retrying (retries_left=%d)", retry_count - 1)
            if retry_count > 0:
                time.sleep(2)
                return call_ai(prompt, temperature, max_tokens, retry_count - 1)
            logger.debug("[AI API] Failed: empty response after all retries")
            return None
            
        logger.debug("[AI API] Success")
        return content
        
    except Exception as e:
        logger.debug("[AI API] Exception: %s, retrying (retries_left=%d)", type(e).__name__, retry_count - 1)
        if retry_count > 0:
            time.sleep(2)
            return call_ai(prompt, temperature, max_tokens, retry_count - 1)
        logger.debug("[AI API] Failed: %s after all retries", type(e).__name__)
        return None
