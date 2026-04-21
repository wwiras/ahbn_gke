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
    churn = df[df["event"] == "churn_triggered"].copy()
    recovered = df[df["event"] == "churn_recovered"].copy()

    run_id = df["run_id"].dropna().iloc[0] if "run_id" in df.columns else "exp11"
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

    return pd.DataFrame([{
        "run_id": run_id,
        "strategy": strategy,
        "failure_mode": "churn",
        "message_count": message_count,
        "avg_delivery_ratio": avg_delivery_ratio,
        "min_delivery_ratio": min_delivery_ratio,
        "avg_propagation_delay": avg_propagation_delay,
        "duplicates": int(len(recv_dup)),
        "total_forwards": int(len(forwards)),
        "churn_events": int(len(churn)),
        "recovered_events": int(len(recovered)),
    }])


def plot_timeline(df: pd.DataFrame, out_png: str) -> None:
    recv = df[df["event"] == "received_new"].copy()
    churn = df[df["event"] == "churn_triggered"].copy()
    recovered = df[df["event"] == "churn_recovered"].copy()

    if recv.empty:
        return

    recv = recv.sort_values("ts")
    recv["delivered_count"] = range(1, len(recv) + 1)
    t0 = min(recv["ts"].min(), churn["ts"].min() if not churn.empty else recv["ts"].min())

    plt.figure(figsize=(9, 4.5))
    plt.plot(recv["ts"] - t0, recv["delivered_count"], label="delivery")

    for i, ts in enumerate(churn["ts"].tolist()):
        plt.axvline(ts - t0, linestyle="--", linewidth=1, label="churn" if i == 0 else None)
    for i, ts in enumerate(recovered["ts"].tolist()):
        plt.axvline(ts - t0, linestyle=":", linewidth=1, label="recovered" if i == 0 else None)

    plt.xlabel("Time since first event (s)")
    plt.ylabel("Cumulative received_new events")
    plt.title("Exp11 dissemination under churn")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()


def plot_adaptation(df: pd.DataFrame, out_png: str) -> None:
    events = df[df["event"].isin(["fanout_changed", "failure_reaction", "mode_switched", "adaptive_state"])].copy()
    churn = df[df["event"] == "churn_triggered"].copy()
    recovered = df[df["event"] == "churn_recovered"].copy()

    if events.empty and churn.empty:
        return

    t0_candidates = []
    if not events.empty:
        t0_candidates.append(events["ts"].min())
    if not churn.empty:
        t0_candidates.append(churn["ts"].min())
    t0 = min(t0_candidates)

    plt.figure(figsize=(9, 4.5))

    if not events.empty:
        events = events.sort_values("ts")
        fanout_points = events.dropna(subset=["fanout", "new_fanout"], how="all").copy()
        fanout_vals = []
        for _, row in fanout_points.iterrows():
            val = row["fanout"] if pd.notna(row.get("fanout", None)) else row.get("new_fanout", None)
            fanout_vals.append(val)
        if fanout_vals:
            plt.plot(fanout_points["ts"] - t0, fanout_vals, marker="o", label="fanout")

        react = events[events["event"] == "failure_reaction"].copy()
        if not react.empty:
            react_vals = []
            for _, row in react.iterrows():
                val = row["fanout"] if pd.notna(row.get("fanout", None)) else row.get("new_fanout", None)
                react_vals.append(val)
            plt.scatter(react["ts"] - t0, react_vals, marker="x", s=70, label="failure reaction")

    for i, ts in enumerate(churn["ts"].tolist()):
        plt.axvline(ts - t0, linestyle="--", linewidth=1, label="churn" if i == 0 else None)
    for i, ts in enumerate(recovered["ts"].tolist()):
        plt.axvline(ts - t0, linestyle=":", linewidth=1, label="recovered" if i == 0 else None)

    plt.xlabel("Time since first adaptive event (s)")
    plt.ylabel("Adaptive state / fanout")
    plt.title("AHBN adaptive trace under churn")
    plt.legend()
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
    summary.to_csv(outdir / "exp11_summary.csv", index=False)
    plot_timeline(df, str(outdir / "exp11_timeline.png"))
    plot_adaptation(df, str(outdir / "exp11_adaptation.png"))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
