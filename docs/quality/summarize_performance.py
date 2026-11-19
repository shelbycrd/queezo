"""Create a compact performance report and align Windows Ollama samples with each run."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path


def read_host_samples(path):
    samples = defaultdict(dict)
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for line in csv.DictReader(stream):
            samples[float(line["utc_epoch"])][int(line["pid"])] = (
                float(line["cpu_s"]), int(line["working_set_bytes"]),
            )
    return samples


def host_resources(scenario, samples):
    start, end = scenario["started_utc_epoch"], scenario["finished_utc_epoch"]
    window = sorted((stamp, values) for stamp, values in samples.items() if start <= stamp <= end)
    by_pid = defaultdict(list)
    for _, values in window:
        for pid, (cpu, _) in values.items():
            by_pid[pid].append(cpu)
    deltas = [max(0, cpu[-1] - cpu[0]) for cpu in by_pid.values() if len(cpu) >= 2]
    return {
        "samples": len(window),
        "cpu_s": sum(deltas) if deltas else None,
        "cpu_sample_span_s": window[-1][0] - window[0][0] if len(window) >= 2 else None,
        "sampled_peak_working_set_bytes": max(
            (sum(memory for _, memory in pids.values()) for _, pids in window), default=None,
        ),
    }


def row_for(scenario, samples):
    row = {key: value for key, value in scenario.items() if key not in {"cards", "sessions"}}
    row["ready"] = sum(s["ready"] for s in scenario["sessions"])
    row["failed"] = sum(s["failed"] for s in scenario["sessions"])
    row["sessions"] = [{key: value for key, value in s.items() if key != "id"} for s in scenario["sessions"]]
    row["host_ollama"] = host_resources(scenario, samples)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    samples = read_host_samples(args.samples)
    report["scenarios"] = [row_for(s, samples) for s in report["scenarios"]]
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
