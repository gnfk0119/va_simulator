import argparse

from simulator.config import load_config
from simulator.runner import SimulationRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartHome VA Simulator")
    parser.add_argument("--config", default="configs/default.json", help="Path to config JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    runner = SimulationRunner(config)
    output_path = runner.run()
    print(f"Simulation complete. Excel saved to: {output_path}")


if __name__ == "__main__":
    main()
