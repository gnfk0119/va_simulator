from __future__ import annotations

import argparse
from pathlib import Path

from src.evaluator import run_observer_evaluation
from src.generator import generate_avatar, generate_environment
from src.simulator import SimulationEngine
from src.exporter import export_logs_to_excel  # 엑셀 모듈

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Home Evaluation Gap Simulator")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["generate", "simulate", "evaluate"],
        help="generate | simulate | evaluate",
    )
    parser.add_argument("--model", default=None, help="OpenAI model name override")
    parser.add_argument(
        "--environment",
        default="data/generated/environment.json",
        help="Path to environment.json",
    )
    parser.add_argument(
        "--avatar",
        default="data/generated/avatar_profile.json",
        help="Path to avatar_profile.json",
    )
    parser.add_argument(
        "--log",
        default="data/logs/simulation_log_full.json",
        help="Path to simulation log",
    )
    parser.add_argument(
        "--evaluation",
        default="data/logs/evaluation_result.json",
        help="Path to evaluation result",
    )
    parser.add_argument(
        "--excel",
        default="data/logs/simulation_report.xlsx",
        help="Path to excel report output",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    environment_path = Path(args.environment)
    avatar_path = Path(args.avatar)
    log_path = Path(args.log)
    evaluation_path = Path(args.evaluation)
    excel_path = Path(args.excel)

    if args.mode == "generate":
        generate_environment(output_path=environment_path, model=args.model)
        generate_avatar(output_path=avatar_path, model=args.model)
        
    elif args.mode == "simulate":
        engine = SimulationEngine(
            environment_path=environment_path,
            avatar_path=avatar_path,
            log_path=log_path,
            model=args.model,
        )
        engine.run()
        # 시뮬레이션 직후에는 '중간 결과'를 엑셀로 저장 (Observer 점수 비어있음)
        print(f"\n📊 Exporting interim simulation logs to Excel: {excel_path}")
        try:
            export_logs_to_excel(json_path=log_path, excel_path=excel_path)
            print("✅ Interim Export completed.")
        except Exception as e:
            print(f"❌ Failed to export Excel: {e}")

    elif args.mode == "evaluate":
        run_observer_evaluation(
            log_path=log_path,
            environment_path=environment_path,
            output_path=evaluation_path,
            model=args.model,
        )
        
        # [핵심 수정] 평가가 끝난 후 '최종 결과(평가 포함)'를 엑셀로 저장
        print(f"\n📊 Exporting FINAL evaluation results to Excel: {excel_path}")
        try:
            # 입력 파일(json_path)을 evaluation_path로 변경하여 평가 점수가 포함된 데이터를 읽음
            export_logs_to_excel(json_path=evaluation_path, excel_path=excel_path)
            print("✅ Final Export completed successfully.")
        except Exception as e:
            print(f"❌ Failed to export Excel: {e}")


if __name__ == "__main__":
    main()