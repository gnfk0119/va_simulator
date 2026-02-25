import json
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def export_to_excel(
    family_path: Path = Path("data/generated/family_profile.json"),
    memory_path: Path = Path("data/logs/memory_history.json"),
    log_path: Path = Path("data/logs/evaluation_result.json"),
    output_dir: Path = Path("data/exports")
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Family Info Export
    family_data = _load_json(family_path)
    if family_data and "members" in family_data:
        family_id = family_data.get("family_id", "unknown")
        members_list = []
        for m in family_data["members"]:
            members_list.append({
                "Family ID": family_id,
                "Member ID": m.get("member_id"),
                "Name": m.get("name"),
                "Role": m.get("role"),
                "Age": m.get("age"),
                "Economic Status": m.get("economic_status"),
                "Monthly Income": m.get("monthly_income"),
                "Bio": m.get("bio")
            })
        df_family = pd.DataFrame(members_list)
        out_family = output_dir / "1_family_info.xlsx"
        df_family.to_excel(out_family, index=False)
        logger.info(f"Exported Family Info to {out_family}")
    else:
        logger.warning(f"Family data not found at {family_path}. Skipping.")

    # 2. Memory History Export
    memory_data = _load_json(memory_path)
    if memory_data:
        mem_list = []
        if isinstance(memory_data, dict):
            for member_id, time_dict in memory_data.items():
                for time_key, items in time_dict.items():
                    for idx, item in enumerate(items):
                        mem_list.append({
                            "Time": time_key,
                            "Index": idx,
                            "Member ID": member_id,
                            "Log Type": item.get("log_type"),
                            "Content": item.get("content"),
                            "Weight": item.get("weight")
                        })
        elif isinstance(memory_data, list):
            from collections import defaultdict
            idx_counter = defaultdict(int)
            for item in memory_data:
                m_id = item.get("member_id", "unknown")
                t = item.get("timestamp", "unknown")
                key = (m_id, t)
                idx = idx_counter[key]
                idx_counter[key] += 1
                mem_list.append({
                    "Time": t,
                    "Index": idx,
                    "Member ID": m_id,
                    "Log Type": item.get("log_type"),
                    "Content": item.get("content"),
                    "Weight": item.get("weight")
                })
        if mem_list:
            df_mem = pd.DataFrame(mem_list)
            df_mem.sort_values(by=["Time", "Member ID", "Index"], inplace=True)
            out_mem = output_dir / "2_memory_history.xlsx"
            df_mem.to_excel(out_mem, index=False)
            logger.info(f"Exported Memory History to {out_mem}")
        else:
            logger.warning("Memory list is empty")
    else:
        logger.warning(f"Memory data not found at {memory_path}. Skipping.")

    # 3. Interaction History Export
    logs_data = _load_json(log_path)
    if logs_data:
        rows = []
        for log in logs_data:
            base_info = {
                "Simulation ID": log.get("simulation_id"),
                "Timestamp": log.get("timestamp"),
                "Family ID": log.get("family_id"),
                "Environment": log.get("environment_type"),
                "Member ID": log.get("member_id"),
                "Member Name": log.get("member_name"),
                "Member Role": log.get("member_role"),
                "Age": log.get("member_age"),
                "Location": log.get("location"),
                "Hourly Activity": log.get("hourly_activity"),
                "Quarterly Activity": log.get("quarterly_activity"),
                "Concrete Action": log.get("concrete_action"),
                "Seed Command": log.get("seed_command"),
                "Used Memories": " | ".join(log.get("shared_memory_refs", []))
            }

            def _extract_interaction(prefix, interaction: dict):
                if not interaction:
                    return {
                        f"{prefix} Command": None,
                        f"{prefix} VA Response": None,
                        f"{prefix} State Changes": None,
                        f"{prefix} Self Rating (SE)": None,
                        f"{prefix} Self Reason": None,
                        f"{prefix} Observer Rating (TE)": None,
                        f"{prefix} Observer Reason": None,
                        f"{prefix} Gap (SE-TE)": None,
                        f"{prefix} Classification": None
                    }
                
                # Format state changes
                changes_str = interaction.get("state_change_description", "")
                if not changes_str:
                    changes = interaction.get("state_changes", [])
                    if changes:
                        changes_str = "; ".join([f"{c['device_name']}.{c['property_name']}: {c['before']}->{c['after']}" for c in changes])
                    else:
                        changes_str = "상태 변화 없음"

                se = interaction.get("self_rating")
                te = interaction.get("observer_rating")
                gap = None
                cls = ""
                if se is not None and te is not None:
                    try:
                        gap = int(se) - int(te)
                        cls = "BG" if gap >= 2 else "SG"
                    except:
                        pass
                
                return {
                    f"{prefix} Command": interaction.get("command"),
                    f"{prefix} VA Response": interaction.get("va_response"),
                    f"{prefix} State Changes": changes_str,
                    f"{prefix} Self Rating (SE)": se,
                    f"{prefix} Self Reason": interaction.get("self_reason"),
                    f"{prefix} Observer Rating (TE)": te,
                    f"{prefix} Observer Reason": interaction.get("observer_reason"),
                    f"{prefix} Gap (SE-TE)": gap,
                    f"{prefix} Classification": cls
                }

            row = dict(base_info)
            row.update(_extract_interaction("[WC/VAC]", log.get("interaction_wc_vac")))
            row.update(_extract_interaction("[WC/VAR]", log.get("interaction_wc_var")))
            row.update(_extract_interaction("[WOC/VAC]", log.get("interaction_woc_vac")))
            row.update(_extract_interaction("[WOC/VAR]", log.get("interaction_woc_var")))
            rows.append(row)

        df_logs = pd.DataFrame(rows)
        out_logs = output_dir / "3_interaction_history.xlsx"
        df_logs.to_excel(out_logs, index=False)
        logger.info(f"Exported Interaction History to {out_logs}")
    else:
        logger.warning(f"Log data not found at {log_path}. Skipping.")

if __name__ == "__main__":
    export_to_excel()
