#!/usr/bin/env bash

set -euo pipefail

ENV_NAME="PhishWalk"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/environment.yml"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
FALLBACK_PIP_INDEX_URL="https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"

cd "${SCRIPT_DIR}"

if ! command -v conda >/dev/null 2>&1; then
    echo "Error: conda is not available on PATH." >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: environment.yml was not found at ${ENV_FILE}." >&2
    exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo "Error: requirements.txt was not found at ${REQUIREMENTS_FILE}." >&2
    exit 1
fi

if conda run -n "${ENV_NAME}" python --version >/dev/null 2>&1; then
    echo "Updating the existing ${ENV_NAME} Conda environment..."
    conda env update -n "${ENV_NAME}" -f "${ENV_FILE}"
else
    echo "Creating the ${ENV_NAME} Conda environment..."
    conda env create -f "${ENV_FILE}"
fi

install_requirements() {
    conda run --no-capture-output -n "${ENV_NAME}" python -m pip install \
        --retries 1 --timeout 20 "$@" --requirement "${REQUIREMENTS_FILE}"
}

if [[ -n "${PHISHWALK_WHEELHOUSE:-}" ]]; then
    if [[ ! -d "${PHISHWALK_WHEELHOUSE}" ]]; then
        echo "Error: PHISHWALK_WHEELHOUSE is not a directory: ${PHISHWALK_WHEELHOUSE}" >&2
        exit 1
    fi
    if ! find "${PHISHWALK_WHEELHOUSE}" -maxdepth 1 -type f -name '*.whl' -print -quit \
        | grep -q .; then
        echo "Error: no wheel files were found in ${PHISHWALK_WHEELHOUSE}." >&2
        exit 1
    fi
    echo "Installing Python dependencies from the offline wheelhouse..."
    INSTALL_SUCCEEDED=false
    if install_requirements \
        --no-index --find-links "${PHISHWALK_WHEELHOUSE}"; then
        INSTALL_SUCCEEDED=true
    fi
elif [[ -n "${PHISHWALK_PIP_INDEX_URL:-}" ]]; then
    echo "Installing Python dependencies from the configured package index..."
    INSTALL_SUCCEEDED=false
    if install_requirements --index-url "${PHISHWALK_PIP_INDEX_URL}"; then
        INSTALL_SUCCEEDED=true
    fi
else
    echo "Installing Python dependencies from the default pip package index..."
    INSTALL_SUCCEEDED=false
    if install_requirements; then
        INSTALL_SUCCEEDED=true
    else
        echo "The default pip index is unavailable; retrying with the TUNA mirror..."
        if install_requirements --index-url "${FALLBACK_PIP_INDEX_URL}"; then
            INSTALL_SUCCEEDED=true
        fi
    fi
fi

if [[ "${INSTALL_SUCCEEDED}" != true ]]; then
    cat >&2 <<'EOF'
Error: Python dependency installation failed.

If this host cannot reach the system pip index, either:
  1. set PHISHWALK_PIP_INDEX_URL to an accessible trusted mirror; or
  2. build an Ubuntu x86-64 wheelhouse with
     bash scripts/build_linux_wheelhouse.sh
     and rerun with PHISHWALK_WHEELHOUSE=/path/to/wheelhouse.
EOF
    exit 1
fi

case "${PHISHWALK_INSTALL_SYSTEM_DEPS:-auto}" in
    auto)
        if [[ "$(uname -s)" == Linux && -f /etc/debian_version ]]; then
            INSTALL_SYSTEM_DEPS=true
        else
            INSTALL_SYSTEM_DEPS=false
        fi
        ;;
    1|true|yes)
        INSTALL_SYSTEM_DEPS=true
        ;;
    0|false|no)
        INSTALL_SYSTEM_DEPS=false
        ;;
    *)
        echo "Error: PHISHWALK_INSTALL_SYSTEM_DEPS must be auto, 0, or 1." >&2
        exit 1
        ;;
esac

if [[ "${INSTALL_SYSTEM_DEPS}" == true ]]; then
    echo "Installing Playwright Chromium system dependencies..."
    conda run --no-capture-output -n "${ENV_NAME}" \
        playwright install-deps chromium
fi

echo "Installing the Playwright Chromium browser..."
if ! conda run --no-capture-output -n "${ENV_NAME}" playwright install chromium; then
    cat >&2 <<'EOF'
Error: Playwright could not install Chromium.

If the Playwright CDN is blocked, provision the matching Linux x86-64 browser
bundle separately and set PLAYWRIGHT_BROWSERS_PATH before rerunning this script.
EOF
    exit 1
fi

echo "Checking installed dependencies..."
conda run --no-capture-output -n "${ENV_NAME}" python -m pip check

echo "Running the core import smoke test..."
conda run --no-capture-output -n "${ENV_NAME}" python -c \
    "
import langchain_anthropic
import langchain_google_genai
import langchain_openai
import langchain_openrouter
from agent.experiment.cli import main

assert callable(main)
print('Core imports passed.')
"

echo "Running the Playwright Chromium smoke test..."
conda run --no-capture-output -n "${ENV_NAME}" python -c \
    "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser = p.chromium.launch(headless=True); page = browser.new_page(); page.set_content('<title>PhishWalk Test</title>'); assert page.title() == 'PhishWalk Test'; browser.close(); p.stop(); print('Playwright Chromium passed.')"

echo
echo "Environment setup completed successfully."
echo "Activate it in your interactive shell with: conda activate ${ENV_NAME}"
