#!/bin/bash
# Test suite runner for Football Rules Expert Bot

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         FOOTBALL RULES EXPERT BOT - TEST SUITE                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

# Activate virtual environment
source venv/bin/activate

# Run tests with coverage
echo "Running test suite with coverage reporting..."
echo

python -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-report=html

echo
echo "✅ Test run complete!"
echo
echo "Coverage report: htmlcov/index.html"
echo
