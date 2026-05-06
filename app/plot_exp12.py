from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def load_jsonl(path: str) -> pd.DataFrame:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, expected_nodes: int) -> pd.DataFrame:
    injected = df[df["event"] == "message_injected"].copy()
    recv_new = df[df["event"] == "received_new"].copy()
    recv_dup = df[df["event"] == "received_duplicate"].copy()
    forwards = df[df["event"] == "forward"].copy()
    overload = df[df["event"].isin(["mixed_resource_applied", "overload_applied"])].copy()
    adaptive = df[df["event"] == "adaptive_state"].copy()

    run_id = df["run_id"].dropna().iloc[0] if "run_id" in df.columns and not df["run_id"].dropna().empty else "exp12"
    strategy = df["strategy"].dropna().iloc[0] if "strategy" in df.columns and not df["strategy"].dropna().empty else "unknown"

    message_count = injected["message_id"].nunique() if not injected.empty else 0
    delivered_counts = recv_new.groupby("message_id")["peer_id"].nunique() if not recv_new.empty else pd.Series(dtype=float)

    delay_per_msg = []
    for msg_id in injected["message_id"].dropna().unique().tolist():
        inject_ts = injected.loc[injected["message_id"] == msg_id, "ts"].min()
        max_recv_ts = recv_new.loc[recv_new["message_id"] == msg_id, "ts"].max()
        if pd.notna(inject_ts) and pd.notna(max_recv_ts):
            delay_per_msg.append(max_recv_ts - inject_ts)

    avg_delivery_ratio = float(delivered_counts.mean() / expected_nodes) if len(delivered_counts) else 0.0
    min_delivery_ratio = float(delivered_counts.min() / expected_nodes) if len(delivered_counts) else 0.0
    avg_propagation_delay = float(sum(delay_per_msg) / len(delay_per_msg)) if delay_per_msg else 0.0

    overloaded_peers = overload["peer_id"].dropna().nunique() if "peer_id" in overload.columns else 0
    avg_fanout = float(adaptive["fanout"].dropna().mean()) if "fanout" in adaptive.columns and not adaptive.empty else 0.0

    return pd.DataFrame([{
        "run_id": run_id,
        "strategy": strategy,
        "failure_mode": "mixed_resources",
        "message_count": int(message_count),
        "avg_delivery_ratio": avg_delivery_ratio,
        "min_delivery_ratio": min_delivery_ratio,
        "avg_propagation_delay": avg_propagation_delay,
        "duplicates": int(len(recv_dup)),
        "total_forwards": int(len(forwards)),
        "overloaded_peers": int(overloaded_peers),
        "avg_adaptive_fanout": avg_fanout,
    }])


def plot_timeline(df: pd.DataFrame, out_png: str) -> None:
    recv = df[df["event"] == "received_new"].copy()
    overload = df[df["event"] == "mixed_resource_applied"].copy()
    if recv.empty:
        return
    recv = recv.sort_values("ts")
    recv["delivered_count"] = range(1, len(recv) + 1)
    t0 = min(recv["ts"].min(), overload["ts"].min() if not overload.empty else recv["ts"].min())

    plt.figure(figsize=(9, 4.5))
    plt.plot(recv["ts"] - t0, recv["delivered_count"], label="delivery")
    for i, ts in enumerate(overload["ts"].dropna().tolist()):
        plt.axvline(ts - t0, linestyle="--", linewidth=1, label="resource stress" if i == 0 else None)
    plt.xlabel("Time since first event (s)")
    plt.ylabel("Cumulative received_new events")
    plt.title("Exp12 dissemination under mixed resources")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def plot_adaptation(df: pd.DataFrame, out_png: str) -> None:
    events = df[df["event"].isin(["adaptive_state", "fanout_changed", "mode_switched"])].copy()
    overload = df[df["event"] == "mixed_resource_applied"].copy()
    if events.empty and overload.empty:
        return

    t0_candidates = []
    if not events.empty:
        t0_candidates.append(events["ts"].min())
    if not overload.empty:
        t0_candidates.append(overload["ts"].min())
    t0 = min(t0_candidates)

    plt.figure(figsize=(9, 4.5))
    if not events.empty:
        fanout_points = events.dropna(subset=["fanout", "new_fanout"], how="all").copy().sort_values("ts")
        vals = []
        for _, row in fanout_points.iterrows():
            vals.append(row["fanout"] if pd.notna(row.get("fanout", None)) else row.get("new_fanout", None))
        if vals:
            plt.plot(fanout_points["ts"] - t0, vals, marker="o", label="fanout")

    for i, ts in enumerate(overload["ts"].dropna().tolist()):
        plt.axvline(ts - t0, linestyle="--", linewidth=1, label="resource stress" if i == 0 else None)

    plt.xlabel("Time since first adaptive/resource event (s)")
    plt.ylabel("Adaptive fanout")
    plt.title("AHBN adaptive trace under mixed resources")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def plot_resource_latency(df: pd.DataFrame, out_png: str) -> None:
    recv = df[df["event"] == "received_new"].copy()
    if recv.empty or "overload_ms" not in recv.columns:
        return
    data = recv.copy()
    data["resource_group"] = data["overload_ms"].fillna(0).apply(lambda x: "overloaded" if float(x) > 0 else "normal")
    grouped = data.groupby("resource_group")["latency_ms"].mean().reset_index()

    plt.figure(figsize=(6, 4))
    plt.bar(grouped["resource_group"], grouped["latency_ms"])
    plt.xlabel("Resource group")
    plt.ylabel("Mean delivery latency (ms)")
    plt.title("Exp12 latency by resource group")
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--expected-nodes", type=int, required=True)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_jsonl(args.log)
    summary = summarize(df, expected_nodes=args.expected_nodes)
    summary.to_csv(outdir / "exp12_summary.csv", index=False)
    plot_timeline(df, str(outdir / "exp12_timeline.png"))
    plot_adaptation(df, str(outdir / "exp12_adaptation.png"))
    plot_resource_latency(df, str(outdir / "exp12_resource_latency.png"))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
