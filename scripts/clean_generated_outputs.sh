#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

find . -name ".DS_Store" -delete
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
rm -rf StateDependentParaformerSimulator/.derivedData

echo "Removed local macOS, Python and Xcode generated files."
