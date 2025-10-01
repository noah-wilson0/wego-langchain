import json
from typing import Any, List

def extract_tools_used(messages: Any) -> List[str]:
    used = set()
    try:
        for m in messages:
            ak = getattr(m, "additional_kwargs", {}) or {}
            for tc in ak.get("tool_calls", []):
                name = (tc.get("function") or {}).get("name")
                if name:
                    used.add(name)
            name_attr = getattr(m, "name", None)
            if name_attr:
                used.add(name_attr)
            content = str(getattr(m, "content", "")) or ""
            if "get_places_page" in content:
                used.add("get_places_page")
    except Exception:
        pass
    return sorted(used)

def last_text(messages: Any) -> str:
    final_msg = next((m for m in reversed(messages) if getattr(m, "content", None)), None)
    if not final_msg:
        raise ValueError("Agent returned no final text message.")
    return str(final_msg.content).strip()

def strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s.replace("json\n", "").replace("\njson", "").strip("`").strip()
    return s

def json_from_agent(messages: Any) -> dict:
    txt = strip_code_fences(last_text(messages))
    return json.loads(txt)
