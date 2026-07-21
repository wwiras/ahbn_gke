#!/usr/bin/env python3
"""
plot_adaptive_decisions.py

Analyse AHBN adaptive controller decisions.

Input
-----
python plot_adaptive_decisions.py outputs/exp8_ahbn-20260721_220742

Output
------
adaptive_decision_trace.csv
adaptive_trigger_frequency.csv
adaptive_mode_transitions.csv
adaptive_summary.txt

adaptive_trigger_frequency.png
adaptive_decision_timeline.png
adaptive_mode_timeline.png
adaptive_fanout_timeline.png
"""

from pathlib import Path
import argparse
import json
import collections

import pandas as pd
import matplotlib.pyplot as plt

TRIGGER_COLOUR = {
    "normal_state": "tab:blue",
    "duplicate_ratio_high": "tab:orange",
    "failure_pressure": "tab:red",
    "bottleneck": "tab:green",
    "overload": "tab:purple",
}

def parse_args():

    parser = argparse.ArgumentParser(
        description="Analyse AHBN adaptive decisions"
    )

    parser.add_argument(
        "experiment",
        help="Experiment folder (e.g. outputs/exp8_ahbn-20260721_220742)"
    )

    return parser.parse_args()

def load_events(log_file):

    events = []

    with open(log_file, "r") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            try:
                events.append(json.loads(line))

            except json.JSONDecodeError:
                continue

    return events

def extract_adaptive(events):

    rows = []

    for e in events:

        if e.get("event") != "adaptive_decision":
            continue

        rows.append({

            "ts":
                e.get("ts"),

            "peer_id":
                e.get("peer_id"),

            "cluster_head":
                e.get("is_cluster_head"),

            "trigger":
                e.get("decision_trigger"),

            "duplicate_ratio":
                e.get("duplicate_ratio"),

            "fail_pressure":
                e.get("fail_pressure"),

            "bottleneck_pressure":
                e.get("bottleneck_pressure"),

            "overload_pressure":
                e.get("overload_pressure"),

            "mode_before":
                e.get("mode_before"),

            "mode_after":
                e.get("mode_after"),

            "fanout_before":
                e.get("fanout_before"),

            "fanout_after":
                e.get("fanout_after"),
        })

    return pd.DataFrame(rows)

def save_trace(df, output_dir):

    outfile = output_dir / "adaptive_decision_trace.csv"

    df.to_csv(
        outfile,
        index=False
    )

    print(
        "Saved",
        outfile
    )

from collections import Counter

def save_trigger_frequency(df, output_dir):

    counts = Counter(df["trigger"])

    freq = (
        pd.DataFrame(
            counts.items(),
            columns=["trigger", "count"]
        )
        .sort_values("count", ascending=False)
    )

    outfile = output_dir / "adaptive_trigger_frequency.csv"

    freq.to_csv(outfile, index=False)

    print("Saved", outfile)

    return freq

def plot_trigger_frequency(freq, output_dir):

    plt.figure(figsize=(8,5))

    plt.bar(
        freq["trigger"],
        freq["count"]
    )

    plt.xticks(rotation=25, ha="right")

    plt.ylabel("Number of decisions")

    plt.xlabel("Decision trigger")

    plt.title("AHBN Adaptive Decision Triggers")

    plt.tight_layout()

    outfile = output_dir / "adaptive_trigger_frequency.png"

    plt.savefig(outfile, dpi=300)

    plt.close()

    print("Saved", outfile)

def save_summary(df, output_dir):

    outfile = output_dir / "adaptive_summary.txt"

    with open(outfile, "w") as f:

        f.write("AHBN Adaptive Decision Summary\n")
        f.write("="*40 + "\n\n")

        f.write(f"Total adaptive decisions : {len(df)}\n")
        f.write(f"Unique peers             : {df['peer_id'].nunique()}\n")
        f.write(f"Cluster heads involved   : {df['cluster_head'].sum()}\n\n")

        f.write("Trigger counts\n")
        f.write("--------------------------\n")

        for trigger, count in df["trigger"].value_counts().items():
            f.write(f"{trigger:25s} {count}\n")

        f.write("\n")

        f.write(
            f"Average duplicate ratio : {df['duplicate_ratio'].mean():.3f}\n"
        )

        f.write(
            f"Maximum duplicate ratio : {df['duplicate_ratio'].max():.3f}\n"
        )

        f.write(
            f"Maximum fail pressure   : {df['fail_pressure'].max():.3f}\n"
        )

        f.write(
            f"Maximum bottleneck      : {df['bottleneck_pressure'].max():.3f}\n"
        )

        f.write(
            f"Maximum overload        : {df['overload_pressure'].max():.3f}\n"
        )

    print("Saved", outfile)

def save_mode_transitions(df, output_dir):

    transitions = (
        df.groupby(["mode_before", "mode_after"])
          .size()
          .reset_index(name="count")
    )

    outfile = output_dir / "adaptive_mode_transitions.csv"

    transitions.to_csv(outfile, index=False)

    print("Saved", outfile)

    return transitions

def plot_mode_transitions(transitions, output_dir):

    labels = (
        transitions["mode_before"]
        + " → "
        + transitions["mode_after"]
    )

    plt.figure(figsize=(7,5))

    plt.bar(labels, transitions["count"])

    plt.ylabel("Number of Decisions")

    plt.xlabel("Mode Transition")

    plt.title("AHBN Mode Transitions")

    plt.xticks(rotation=20)

    plt.tight_layout()

    outfile = output_dir / "adaptive_mode_transitions.png"

    plt.savefig(outfile, dpi=300)

    plt.close()

    print("Saved", outfile)

def plot_fanout_timeline(df, output_dir):

    timeline = df.copy()
    timeline = timeline.sort_values("ts")
    timeline["step"] = range(len(timeline))

    plt.figure(figsize=(10,4))

    plt.plot(
        timeline["step"],
        timeline["fanout_after"],
        linewidth=1.8,
    )

    plt.xlabel("Adaptive Decision")
    plt.ylabel("Fanout")
    plt.title("AHBN Fanout Adaptation Timeline")

    plt.grid(True, alpha=0.3)

    plt.tight_layout()

    outfile = output_dir / "adaptive_fanout_timeline.png"

    plt.savefig(outfile, dpi=300)

    plt.close()

    print("Saved", outfile)

def plot_decision_timeline(df, output_dir):

    timeline = df.copy()
    timeline = timeline.sort_values("ts")
    timeline["step"] = range(len(timeline))

    plt.figure(figsize=(12,4))

    for trigger, group in timeline.groupby("trigger"):

        plt.scatter(
            group["step"],
            [trigger] * len(group),
            s=20,
            color=TRIGGER_COLOUR.get(trigger, "gray"),
            label=trigger,
        )

    plt.xlabel("Adaptive Decision")
    plt.ylabel("Decision Trigger")
    plt.title("AHBN Adaptive Decision Timeline")

    plt.legend()

    plt.tight_layout()

    outfile = output_dir / "adaptive_decision_timeline.png"

    plt.savefig(outfile, dpi=300)

    plt.close()

    print("Saved", outfile)

def main():
    
    args = parse_args()

    experiment = Path(args.experiment).resolve()

    logfile = experiment / "logs.jsonl"

    if not logfile.exists():
        raise FileNotFoundError(logfile)

    # 1. Load events
    events = load_events(logfile)

    # 2. Extract adaptive decisions
    decisions = extract_adaptive(events)

    # 3. Save trace
    save_trace(decisions, experiment)

    # 4. Trigger statistics
    freq = save_trigger_frequency(decisions, experiment)
    plot_trigger_frequency(freq, experiment)

    # 5. Summary
    save_summary(decisions, experiment)

    # 6. Mode transitions
    transitions = save_mode_transitions(decisions, experiment)
    plot_mode_transitions(transitions, experiment)

    # 7. Timeline plots
    plot_fanout_timeline(decisions, experiment)
    plot_decision_timeline(decisions, experiment)

def main():

    args = parse_args()

    experiment = Path(args.experiment).resolve()

    logfile = experiment / "logs.jsonl"

    if not logfile.exists():
        raise FileNotFoundError(logfile)

    events = load_events(logfile)

    decisions = extract_adaptive(events)

    save_trace(decisions, experiment)

    freq = save_trigger_frequency(decisions, experiment)
    plot_trigger_frequency(freq, experiment)

    save_summary(decisions, experiment)

    transitions = save_mode_transitions(decisions, experiment)
    plot_mode_transitions(transitions, experiment)

    plot_fanout_timeline(decisions, experiment)

    plot_decision_timeline(decisions, experiment)


if __name__ == "__main__":
    main()
