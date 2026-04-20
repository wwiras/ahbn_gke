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


def summarize(df: pd.DataFrame, expected_nodes: int | None = None) -> pd.DataFrame:
    run_id = df["run_id"].dropna().iloc[0] if "run_id" in df.columns else "unknown"
    inject_ts = df.loc[df["event"] == "message_injected", "ts"].min()
    fail_ts = df.loc[df["event"] == "failure_triggered", "ts"].min()
    
    if pd.notna(fail_ts):
        # plt.axvline(x=fail_ts - t0, linestyle="--", linewidth=1)
        pass

    received_new = df[df["event"] == "received_new"].copy()
    received_dup = df[df["event"] == "received_duplicate"].copy()
    forwards = df[df["event"] == "forward"].copy()

    delivered_peers = received_new["peer_id"].nunique() if not received_new.empty else 0
    duplicates = len(received_dup)
    total_forwards = len(forwards)

    if expected_nodes is None:
        expected_nodes = int(df["peer_id"].dropna().max()) + 1 if "peer_id" in df.columns else delivered_peers

    delivery_ratio = delivered_peers / expected_nodes if expected_nodes > 0 else 0.0
    propagation_delay = (received_new["ts"].max() - inject_ts) if not received_new.empty else None
    recovery_time = (received_new["ts"].max() - fail_ts) if not received_new.empty and pd.notna(fail_ts) else None

    strategy = df["strategy"].dropna().iloc[0] if "strategy" in df.columns and not df["strategy"].dropna().empty else "unknown"
    failure_mode = None
    ft = df[df["event"] == "failure_triggered"]
    if not ft.empty and "failure_mode" in ft.columns:
        failure_mode = ft["failure_mode"].iloc[0]

    return pd.DataFrame([{
        "run_id": run_id,
        "strategy": strategy,
        "failure_mode": failure_mode,
        "delivery_ratio": delivery_ratio,
        "propagation_delay": propagation_delay,
        "duplicates": duplicates,
        "total_forwards": total_forwards,
        "recovery_time": recovery_time,
        "delivered_peers": delivered_peers,
        "expected_nodes": expected_nodes,
    }])


def plot_timeline(df: pd.DataFrame, out_png: str) -> None:
    recv = df[df["event"] == "received_new"].copy()
    fail = df[df["event"] == "failure_triggered"].copy()

    if recv.empty:
        return

    recv = recv.sort_values("ts")
    recv["delivered_count"] = range(1, len(recv) + 1)

    t0 = recv["ts"].min()

    plt.figure(figsize=(8, 4))
    plt.plot(recv["ts"] - t0, recv["delivered_count"], label="delivery")

    # ✅ Correct failure marker
    if not fail.empty:
        fail_ts = fail["ts"].min()
        plt.axvline(x=fail_ts - t0, linestyle="--", linewidth=1, label="failure")

    plt.xlabel("Time since first delivery (s)")
    plt.ylabel("Cumulative delivered peers")
    plt.title("Exp10 dissemination timeline")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()

def plot_adaptation(df: pd.DataFrame, out_png: str) -> None:
    events = df[df["event"].isin(["fanout_changed", "failure_reaction"])].copy()
    fail = df[df["event"] == "failure_triggered"].copy()

    plt.figure(figsize=(8, 4))

    if not events.empty:
        events = events.sort_values("ts")
        t0 = events["ts"].min()

        # Use explicit fanout field when available, otherwise fallback to new_fanout
        fanout_vals = []
        for _, row in events.iterrows():
            if pd.notna(row.get("fanout", None)):
                fanout_vals.append(row["fanout"])
            elif pd.notna(row.get("new_fanout", None)):
                fanout_vals.append(row["new_fanout"])
            else:
                fanout_vals.append(None)

        plt.plot(
            events["ts"] - t0,
            fanout_vals,
            marker="o",
            label="fanout",
        )

        # Mark explicit failure reactions so they are visually obvious
        react = events[events["event"] == "failure_reaction"]
        if not react.empty:
            react_vals = []
            for _, row in react.iterrows():
                if pd.notna(row.get("fanout", None)):
                    react_vals.append(row["fanout"])
                elif pd.notna(row.get("new_fanout", None)):
                    react_vals.append(row["new_fanout"])
                else:
                    react_vals.append(None)

            plt.scatter(
                react["ts"] - t0,
                react_vals,
                marker="x",
                s=70,
                label="failure reaction",
            )

        if not fail.empty:
            fail_ts = fail["ts"].min()
            plt.axvline(
                x=fail_ts - t0,
                linestyle="--",
                linewidth=1,
                label="failure",
            )

        plt.legend()

    plt.xlabel("Time (s)")
    plt.ylabel("Adaptive state")
    plt.title("AHBN adaptation trace")
    plt.tight_layout()
    plt.savefig(out_png, dpi=180)
    plt.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--expected-nodes", type=int, default=None)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_jsonl(args.log)
    summary = summarize(df, expected_nodes=args.expected_nodes)
    summary.to_csv(outdir / "exp10_summary.csv", index=False)
    plot_timeline(df, str(outdir / "exp10_timeline.png"))
    plot_adaptation(df, str(outdir / "exp10_adaptation.png"))

    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()