from pathlib import Path
from typing import Any, Dict, List

from openpyxl import Workbook


def _write_sheet(wb: Workbook, title: str, rows: List[Dict[str, Any]]) -> None:
    ws = wb.create_sheet(title)
    if not rows:
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])


def export_to_excel(output_path: str, logs: Dict[str, List[Dict[str, Any]]]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # Remove default sheet
    default = wb.active
    wb.remove(default)

    _write_sheet(wb, "public_state_log", logs.get("public_state_log", []))
    _write_sheet(wb, "private_state_log", logs.get("private_state_log", []))
    _write_sheet(wb, "dialogue_log", logs.get("dialogue_log", []))
    _write_sheet(wb, "self_rating", logs.get("self_rating_log", []))
    _write_sheet(wb, "third_party_rating", logs.get("third_party_rating_log", []))

    wb.save(path)
