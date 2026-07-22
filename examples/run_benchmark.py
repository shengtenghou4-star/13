from __future__ import annotations

import argparse
import json
from pathlib import Path

from houearth.benchmarks import BENCHMARKS, run_known_planet_benchmark

parser = argparse.ArgumentParser()
parser.add_argument("key", choices=sorted(BENCHMARKS))
parser.add_argument("--output", type=Path)
args = parser.parse_args()
output = args.output or Path("outputs/benchmarks") / args.key
result = run_known_planet_benchmark(args.key, output_dir=output)
print(json.dumps(result, indent=2))
