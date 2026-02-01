# main.py
from __future__ import annotations

import argparse
from pathlib import Path

# Config 로더 임포트
from src.config import config
from src.evaluator import run_observer_evaluation
from src.generator import generate_avatar, generate_environment
from src.simulator import SimulationEngine
from src.exporter import export_logs_to_excel

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Home Evaluation Gap Simulator")
    parser.add_argument("--mode", required=True, choices=["generate", "simulate", "evaluate"])
    # 모델 오버라이드 옵션
    parser.add_argument("--model", default=None, help="OpenAI model name override")
    args = parser.parse_args()

    # 1. Config 로드 (경로 및 설정값)
    env_path = Path(config["paths"]["environment"])
    avatar_dir = Path(config["paths"]["avatar_dir"])
    log_dir = Path(config["paths"]["log_dir"])
    
    # 모델명 결정 (인자값 우선, 없으면 Config 값)
    model_name = args.model if args.model else config["simulation"]["model_name"]
    num_profiles = config["simulation"]["num_profiles"]  # 5

    # 디렉토리 생성
    avatar_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # 1. GENERATE 모드
    # ----------------------------------------------------------------
    if args.mode == "generate":
        print("🛠️  [Generate Mode] Started...")
        
        # (A) 환경 생성 (1회 공통)
        if not env_path.exists():
            print(f"🏠 Generating Single Environment at {env_path}...")
            generate_environment(output_path=env_path, model=model_name)
        else:
            print(f"🏠 Environment already exists. Using existing: {env_path}")

        # (B) 아바타 생성 (5명)
        print(f"👥 Generating {num_profiles} Avatar Profiles...")
        for i in range(num_profiles):
            profile_path = avatar_dir / f"avatar_{i}.json"
            print(f"  - [{i+1}/{num_profiles}] Creating Avatar -> {profile_path.name}")
            generate_avatar(output_path=profile_path, model=model_name)
        
        print("✅ Data Generation Complete.")

    # ----------------------------------------------------------------
    # 2. SIMULATE 모드
    # ----------------------------------------------------------------
    elif args.mode == "simulate":
        print("🏃 [Simulate Mode] Started...")
        
        # 생성된 모든 아바타 파일 찾기
        profile_files = sorted(list(avatar_dir.glob("avatar_*.json")))
        
        if not profile_files:
            print("❌ No profiles found. Please run '--mode generate' first.")
            return

        for profile_path in profile_files:
            profile_id = profile_path.stem  # e.g., "avatar_0"
            log_path = log_dir / f"log_{profile_id}.json"
            excel_path = log_dir / f"report_{profile_id}.xlsx"
            
            # [중요] 각 시뮬레이션은 독립적으로 실행됩니다.
            # (SimulationEngine이 매번 env_path에서 원본 환경을 새로 로드함)
            print(f"\n🚀 Simulating: {profile_id} (Model: {model_name})")
            
            engine = SimulationEngine(
                environment_path=env_path,  # 5명 모두 같은 집(환경) 사용
                avatar_path=profile_path,
                log_path=log_path,
                model=model_name,
            )
            engine.run()
            
            # 중간 결과 엑셀 저장
            try:
                export_logs_to_excel(json_path=log_path, excel_path=excel_path)
                print(f"  ✅ Exported interim report: {excel_path.name}")
            except Exception as e:
                print(f"  ❌ Export failed: {e}")

    # ----------------------------------------------------------------
    # 3. EVALUATE 모드
    # ----------------------------------------------------------------
    elif args.mode == "evaluate":
        print("⚖️  [Evaluate Mode] Started...")
        
        log_files = sorted(list(log_dir.glob("log_avatar_*.json")))
        
        if not log_files:
            print("❌ No logs found. Please run '--mode simulate' first.")
            return

        for log_path in log_files:
            profile_id = log_path.stem.replace("log_", "")
            eval_result_path = log_dir / f"eval_{profile_id}.json"
            final_excel_path = log_dir / f"final_report_{profile_id}.xlsx"
            
            print(f"\n👀 Evaluating: {profile_id}")
            
            run_observer_evaluation(
                log_path=log_path,
                environment_path=env_path,
                output_path=eval_result_path,
                model=model_name,
            )
            
            try:
                export_logs_to_excel(json_path=eval_result_path, excel_path=final_excel_path)
                print(f"  ✅ Final Report Saved: {final_excel_path.name}")
            except Exception as e:
                print(f"  ❌ Export failed: {e}")

if __name__ == "__main__":
    main()