from __future__ import annotations

import argparse
from pathlib import Path

from src.evaluator import run_observer_evaluation
from src.generator import generate_avatar, generate_environment
from src.simulator import SimulationEngine


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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    environment_path = Path(args.environment)
    avatar_path = Path(args.avatar)
    log_path = Path(args.log)
    evaluation_path = Path(args.evaluation)

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
    elif args.mode == "evaluate":
        run_observer_evaluation(
            log_path=log_path,
            environment_path=environment_path,
            output_path=evaluation_path,
            model=args.model,
        )


if __name__ == "__main__":
    main()
