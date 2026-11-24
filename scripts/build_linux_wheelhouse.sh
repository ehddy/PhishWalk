#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
OUTPUT_DIRECTORY="${1:-${PROJECT_ROOT}/wheelhouse-linux-x86_64}"
PYTHON_COMMAND="${PYTHON_COMMAND:-python3}"

if ! command -v "${PYTHON_COMMAND}" >/dev/null 2>&1; then
    echo "Error: ${PYTHON_COMMAND} is not available on PATH." >&2
    exit 1
fi

mkdir -p "${OUTPUT_DIRECTORY}"

"${PYTHON_COMMAND}" -m pip download \
    --dest "${OUTPUT_DIRECTORY}" \
    --only-binary=:all: \
    --platform manylinux_2_28_x86_64 \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 311 \
    --abi cp311 \
    --abi abi3 \
    --abi none \
    --requirement "${REQUIREMENTS_FILE}"

echo
echo "Linux x86-64 wheelhouse created at: ${OUTPUT_DIRECTORY}"
echo "Copy this directory to the server, then run:"
echo "  PHISHWALK_WHEELHOUSE=${OUTPUT_DIRECTORY} bash setup_environment.sh"
