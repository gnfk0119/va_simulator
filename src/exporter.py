import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

def export_logs_to_excel(
    json_path: Path,
    excel_path: Path
) -> None:
    """
    JSON 로그 파일을 읽어 엑셀 리포트로 변환합니다.
    """
    if not json_path.exists():
        print(f"⚠️ Log file not found at {json_path}")
        return

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("⚠️ No data found in logs.")
        return

    # 데이터 평탄화 (Flattening)
    records = []
    for entry in data:
        # State Changes 리스트를 보기 좋은 문자열로 변환
        changes_str = _format_state_changes(entry.get("state_changes", []))
        
        row = {
            "Time": entry.get("time"),
            "Visible Action": entry.get("visible_action"),
            "Hidden Context": entry.get("hidden_context"),
            "Command": entry.get("command"),
            "VA Response": entry.get("va_response"),
            "State Changes": changes_str,
            "Self Rating": entry.get("self_rating"),
            "Self Reason": entry.get("self_reason"),
            "Observer Rating": entry.get("observer_rating", ""),
            "Observer Reason": entry.get("observer_reason", "")
        }
        records.append(row)

    df = pd.DataFrame(records)
    
    # 엑셀 파일 저장 (폴더가 없으면 생성)
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(excel_path, index=False)
    print(f"✅ Excel saved to {excel_path}")

def _format_state_changes(changes: List[Dict[str, Any]]) -> str:
    if not changes:
        return "-"
    
    lines = []
    for c in changes:
        # device_name.property: before -> after
        line = f"{c.get('device_name')}.{c.get('property_name')}: {c.get('before')} -> {c.get('after')}"
        lines.append(line)
    
    return "\n".join(lines)