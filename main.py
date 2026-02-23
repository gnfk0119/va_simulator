from __future__ import annotations

import argparse
import random
from pathlib import Path

from src.config import config
from src.evaluator import run_observer_evaluation
from src.generator import generate_family_and_schedules, generate_environment
from src.simulator import SimulationEngine
from src.exporter import export_to_excel

# (옵션) 환경 생성 시드 (간소화)
ENV_VIBES = ["모던", "내추럴", "미니멀", "북유럽"]

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Home Evaluation Gap Simulator")
    parser.add_argument("--mode", required=True, choices=["generate", "simulate", "evaluate"])
    parser.add_argument("--model", default=None, help="OpenAI model name override")
    return parser

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Paths
    env_dir = Path("data/generated/environments")
    family_dir = Path("data/generated/families")
    log_dir = Path("data/logs")
    export_dir = Path("data/exports")
    
    model_name = args.model if args.model else config["simulation"]["model_name"]
    # 예시로 1개만 기본 실행하거나, config.yaml의 num_profiles 활용
    num_runs = config["simulation"].get("num_profiles", 1)

    env_dir.mkdir(parents=True, exist_ok=True)
    family_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # 1. GENERATE 모드
    # ----------------------------------------------------------------
    if args.mode == "generate":
        print(f"🛠️  [Generate Mode] Started ({num_runs} setups)...")
        
        for i in range(num_runs):
            env_path = env_dir / f"environment_{i}.json"
            family_path = family_dir / f"family_{i}.json"
            
            # 1. Environment 생성
            vibe = random.choice(ENV_VIBES)
            print(f"  [{i}] Generating Environment (Vibe: {vibe})...")
            generate_environment(output_path=env_path, model=model_name, theme_hint=vibe)

            # 2. Family & Schedule 생성
            print(f"  [{i}] Generating Family & Schedules from time use survey...")
            # 기본적으로 src 폴더 외부에 있는 생활시간조사 엑셀 파일 참조
            generate_family_and_schedules(output_path=family_path, survey_data_path="생활시간조사.xlsx", model=model_name)
        
        print("✅ Data Generation Complete.")

    # ----------------------------------------------------------------
    # 2. SIMULATE 모드
    # ----------------------------------------------------------------
    elif args.mode == "simulate":
        print("🏃 [Simulate Mode] Started...")
        
        family_files = sorted(list(family_dir.glob("family_*.json")))
        if not family_files:
            print("❌ No family profiles found.")
            return

        for family_path in family_files:
            try:
                run_id = int(family_path.stem.split("_")[1])
            except ValueError:
                continue

            env_path = env_dir / f"environment_{run_id}.json"
            log_path = log_dir / f"simulation_log_{run_id}.json"
            
            if not env_path.exists():
                print(f"⚠️ Env {env_path} not found. Skipping {run_id}.")
                continue

            print(f"\n🚀 Simulating: Family {run_id} @ Env {run_id}")
            engine = SimulationEngine(
                environment_path=env_path,
                family_path=family_path,
                log_path=log_path,
                model=model_name,
            )
            # Memory History는 SimulationEngine 실행 시 log_dir에 memory_history.json으로 저장됨 
            # (여러 run이 있으면 덮어쓰거나 수정 필요하지만 여기서는 단순 데모로 진행)
            engine.run()

        print("\n✅ All Simulations Completed.")

    # ----------------------------------------------------------------
    # 3. EVALUATE 모드
    # ----------------------------------------------------------------
    elif args.mode == "evaluate":
        print("⚖️  [Evaluate Mode] Started...")
        
        log_files = sorted(list(log_dir.glob("simulation_log_*.json")))
        if not log_files:
            print("❌ No logs found. Run simulate first.")
            return

        for log_path in log_files:
            try:
                run_id = int(log_path.stem.split("_")[2])
            except ValueError:
                continue
            
            env_path = env_dir / f"environment_{run_id}.json"
            family_path = family_dir / f"family_{run_id}.json"
            eval_result_path = log_dir / f"eval_result_{run_id}.json"
            
            if not env_path.exists():
                continue

            print(f"\n👀 Evaluating Simulation {run_id}...")
            run_observer_evaluation(
                log_path=log_path,
                environment_path=env_path,
                output_path=eval_result_path,
                model=model_name,
            )

            # Export to Excel
            # 다수의 파일이 있는 경우 단일 run_id를 기준으로 저장하도록 이름 분리
            run_export_dir = export_dir / f"run_{run_id}"
            print(f"📊 Exporting Excel Reports for Run {run_id}...")
            export_to_excel(
                family_path=family_path,
                memory_path=log_dir / "memory_history.json",
                log_path=eval_result_path,
                output_dir=run_export_dir
            )

        print("\n🎉 Evaluation and Export Completed.")

if __name__ == "__main__":
    main()