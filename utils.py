# utils.py (

import json
from typing import Any, List

_TOOL_NAMES = {"get_places_page", "search_place_by_title"}

def _scan_text_for_tools(text: str) -> List[str]:
    # 월러스 연산자 사용 제거
    return [name for name in _TOOL_NAMES if name in text]

def extract_tools_used(messages: Any) -> List[str]:
    used = set()
    try:
        for m in messages:
            ak = getattr(m, "additional_kwargs", {}) or {}

            # 1) OpenAI-style multi-tool calls
            for tc in ak.get("tool_calls", []):
                fn = (tc.get("function") or {}).get("name")
                if fn and fn in _TOOL_NAMES:
                    used.add(fn)

            # 2) Single function_call (some providers)
            fc = ak.get("function_call") or {}
            fn2 = fc.get("name")
            if fn2 and fn2 in _TOOL_NAMES:
                used.add(fn2)

            # 3) name 속성
            name_attr = getattr(m, "name", None)
            if name_attr and name_attr in _TOOL_NAMES:
                used.add(name_attr)

            # 4) content 텍스트 스캔 (백업 탐지)
            content = getattr(m, "content", "")
            try:
                content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            except Exception:
                content_str = str(content)
            for hit in _scan_text_for_tools(content_str):
                used.add(hit)

    except Exception:
        pass

    return sorted(used)


def last_text(messages: Any) -> str:
    final_msg = next((m for m in reversed(messages) if getattr(m, "content", None) is not None), None)
    if not final_msg:
        raise ValueError("Agent returned no final text message.")
    c = getattr(final_msg, "content", "")
    if isinstance(c, str):
        return c.strip()
    try:
        return json.dumps(c, ensure_ascii=False).strip()
    except Exception:
        return str(c).strip()


def strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.lstrip("`").lstrip()
        if "\n" in s:
            first_line, rest = s.split("\n", 1)
            if first_line.strip().lower() in {"json", "python", "javascript", "ts", "typescript", "yaml", "yml"}:
                s = rest
            else:
                s = first_line + "\n" + rest
        s = s.rstrip("`").strip()
    return s


def json_from_agent(messages: Any) -> dict:
    txt = strip_code_fences(last_text(messages))
    return json.loads(txt)
