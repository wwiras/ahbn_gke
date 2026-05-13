from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    if not path.exists():
        return pd.DataFrame()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return pd.DataFrame(rows)


def summarize_run(df: pd.DataFrame, expected_nodes: int) -> dict:
    if df.empty:
        return {}

    run_id = df["run_id"].dropna().iloc[0] if "run_id" in df else "unknown"
    strategy = df["strategy"].dropna().iloc[0] if "strategy" in df and not df["strategy"].dropna().empty else run_id

    injected = df[df["event"] == "message_injected"].copy()
    new = df[df["event"] == "received_new"].copy()
    dup = df[df["event"] == "received_duplicate"].copy()
    fwd = df[df["event"] == "forward"].copy()
    bottleneck = df[df["event"].isin(["bottleneck_started", "overload_applied", "bottleneck_applied"])].copy()

    message_ids = sorted(set(injected.get("message_id", [])))
    per_message_delays = []
    delivered_pairs = set()

    for mid in message_ids:
        inj = injected[injected["message_id"] == mid]
        rec = new[new["message_id"] == mid]
        if inj.empty or rec.empty:
            continue
        t0 = inj["ts"].min()
        delivered_pairs.update((mid, int(x)) for x in rec["peer_id"].dropna())
        per_message_delays.append(float(rec["ts"].max() - t0))

    expected_deliveries = max(1, expected_nodes * max(1, len(message_ids)))
    delivery_ratio = len(delivered_pairs) / expected_deliveries

    return {
        "run_id": run_id,
        "strategy": strategy,
        "messages": len(message_ids),
        "delivery_ratio": delivery_ratio,
        "avg_propagation_delay_s": sum(per_message_delays) / len(per_message_delays) if per_message_delays else None,
        "p95_propagation_delay_s": pd.Series(per_message_delays).quantile(0.95) if per_message_delays else None,
        "duplicates": len(dup),
        "total_forwards": len(fwd),
        "duplicate_per_message": len(dup) / max(1, len(message_ids)),
        "forwards_per_message": len(fwd) / max(1, len(message_ids)),
        "bottleneck_events": len(bottleneck),
    }


def plot_bars(summary: pd.DataFrame, outdir: Path) -> None:
    order = ["cluster", "ahbn", "gossip"]
    df = summary.copy()
    df["strategy"] = pd.Categorical(df["strategy"], categories=order, ordered=True)
    df = df.sort_values("strategy")

    for metric, ylabel, fname in [
        ("avg_propagation_delay_s", "Average propagation delay (s)", "comparison_delay.png"),
        ("duplicates", "Duplicate receptions", "comparison_duplicates.png"),
        ("total_forwards", "Forward transmissions", "comparison_forwards.png"),
        ("delivery_ratio", "Delivery ratio", "comparison_delivery.png"),
    ]:
        plt.figure(figsize=(6.5, 4))
        plt.bar(df["strategy"].astype(str), df[metric])
        plt.xlabel("Strategy")
        plt.ylabel(ylabel)
        plt.title(f"Exp8 AHBN vs Cluster vs Gossip: {ylabel}")
        plt.tight_layout()
        plt.savefig(outdir / fname, dpi=220)
        plt.close()


def plot_timeline(run_dirs: list[Path], outdir: Path) -> None:
    plt.figure(figsize=(8, 4.5))

    for d in run_dirs:
        df = load_jsonl(d / "logs.jsonl")
        if df.empty:
            continue
        strategy = df["strategy"].dropna().iloc[0] if "strategy" in df and not df["strategy"].dropna().empty else d.name
        new = df[df["event"] == "received_new"].copy().sort_values("ts")
        inj = df[df["event"] == "message_injected"].copy()
        if new.empty or inj.empty:
            continue
        t0 = inj["ts"].min()
        new["cum_new_deliveries"] = range(1, len(new) + 1)
        plt.plot(new["ts"] - t0, new["cum_new_deliveries"], label=strategy)

    plt.xlabel("Time since first injection (s)")
    plt.ylabel("Cumulative new deliveries")
    plt.title("Exp8 dissemination progress under CH bottleneck")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / "comparison_timeline.png", dpi=220)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dirs", nargs="+", required=True)
    ap.add_argument("--expected-nodes", type=int, default=20)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    run_dirs = [Path(x) for x in args.run_dirs]

    rows = []
    for d in run_dirs:
        row = summarize_run(load_jsonl(d / "logs.jsonl"), args.expected_nodes)
        if row:
            rows.append(row)

    summary = pd.DataFrame(rows)
    summary.to_csv(outdir / "exp8_strategy_comparison.csv", index=False)

    if not summary.empty:
        plot_bars(summary, outdir)
        plot_timeline(run_dirs, outdir)
        print(summary.to_string(index=False))
    else:
        print("No valid logs found.")


if __name__ == "__main__":
    main()
