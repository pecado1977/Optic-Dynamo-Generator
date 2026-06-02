#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

xcodebuild \
  -project StateDependentParaformerSimulator/StateDependentParaformerSimulator.xcodeproj \
  -scheme StateDependentParaformerSimulator \
  -configuration Debug \
  -derivedDataPath StateDependentParaformerSimulator/.derivedData \
  build \
  CODE_SIGNING_ALLOWED=NO

echo
echo "Built app:"
echo "  StateDependentParaformerSimulator/.derivedData/Build/Products/Debug/StateDependentParaformerSimulator.app"
