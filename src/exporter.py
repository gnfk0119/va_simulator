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
                "Traits": m.get("traits")
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
        for m in memory_data:
            mem_list.append({
                "Time": m.get("time"),
                "Member ID": m.get("member_id"),
                "Description": m.get("description"),
                "Decay Weight": m.get("decay_weight"),
                "Shared With": ", ".join(m.get("shared_with", []))
            })
        df_memory = pd.DataFrame(mem_list)
        out_memory = output_dir / "2_memory_history.xlsx"
        df_memory.to_excel(out_memory, index=False)
        logger.info(f"Exported Memory History to {out_memory}")
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
                "Concrete Action": log.get("concrete_action"),
                "Latent Command": log.get("latent_command"),
                "Used Memories": " | ".join(log.get("shared_memory_refs", []))
            }

            def _extract_interaction(prefix, interaction: dict):
                if not interaction:
                    return {}
                
                # Format state changes
                changes_str = interaction.get("state_change_description", "")
                if not changes_str:
                    changes = interaction.get("state_changes", [])
                    if changes:
                        changes_str = "; ".join([f"{c['device_name']}.{c['property_name']}: {c['before']}->{c['after']}" for c in changes])
                    else:
                        changes_str = "상태 변화 없음"

                return {
                    f"{prefix} Command": interaction.get("command"),
                    f"{prefix} VA Response": interaction.get("va_response"),
                    f"{prefix} State Changes": changes_str,
                    f"{prefix} Self Rating": interaction.get("self_rating"),
                    f"{prefix} Self Reason": interaction.get("self_reason"),
                    f"{prefix} Observer Rating": interaction.get("observer_rating"),
                    f"{prefix} Observer Reason": interaction.get("observer_reason")
                }

            row = dict(base_info)
            row.update(_extract_interaction("With-Context", log.get("interaction_with_context")))
            row.update(_extract_interaction("Without-Context", log.get("interaction_without_context")))
            rows.append(row)

        df_logs = pd.DataFrame(rows)
        out_logs = output_dir / "3_interaction_history.xlsx"
        df_logs.to_excel(out_logs, index=False)
        logger.info(f"Exported Interaction History to {out_logs}")
    else:
        logger.warning(f"Log data not found at {log_path}. Skipping.")

if __name__ == "__main__":
    export_to_excel()