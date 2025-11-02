#!/bin/bash
# Run all DetectK tests

set -e

echo "=== Running DetectK Tests ==="
echo ""

# Core package
echo "Testing core..."
cd packages/core && python3 -m pytest tests/ -q && cd ../..

# Detectors
echo "Testing detectors..."
cd packages/detectors/core && python3 -m pytest tests/ -q && cd ../../..

# Alerters
echo "Testing alerters..."
cd packages/alerters/mattermost && python3 -m pytest tests/ -q && cd ../../..

# Collectors
echo "Testing collectors..."
cd packages/collectors/clickhouse && python3 -m pytest tests/ -q && cd ../../..
cd packages/collectors/http && python3 -m pytest tests/ -q && cd ../../..
cd packages/collectors/sql && python3 -m pytest tests/ -q && cd ../../..

echo ""
echo "=== All Tests Passed! ==="
