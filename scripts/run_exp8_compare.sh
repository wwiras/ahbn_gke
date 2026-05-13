#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${DIR}/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
COMPARE_OUT="${ROOT_DIR}/outputs/exp8_compare-${STAMP}"
mkdir -p "${COMPARE_OUT}"

run_one() {
  local strategy="$1"
  local cfg="experiments/exp8_${strategy}.yaml"
  echo "=== Running Exp8 ${strategy} ==="
  NAMESPACE="${NAMESPACE:-ahbn-exp8-compare}" \
  RELEASE="ahbn" \
  "${DIR}/run_experiment.sh" "${cfg}"
}

run_one ahbn
run_one cluster
run_one gossip

AHBN_DIR="$(ls -td "${ROOT_DIR}"/outputs/exp8_ahbn-* | head -1)"
CLUSTER_DIR="$(ls -td "${ROOT_DIR}"/outputs/exp8_cluster-* | head -1)"
GOSSIP_DIR="$(ls -td "${ROOT_DIR}"/outputs/exp8_gossip-* | head -1)"

python "${ROOT_DIR}/app/plot_compare.py" \
  --run-dirs "${AHBN_DIR}" "${CLUSTER_DIR}" "${GOSSIP_DIR}" \
  --expected-nodes 20 \
  --outdir "${COMPARE_OUT}"

echo "DONE comparison -> ${COMPARE_OUT}"
