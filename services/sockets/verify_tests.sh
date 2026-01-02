#\!/bin/bash
# Verification script for test suite

echo "=== Sockets Service MQ Test Suite Verification ==="
echo ""

echo "📁 Test Files:"
ls -lh tests/test_mq_*.py
echo ""

echo "📊 Test Statistics:"
echo "  test_mq_core.py:      $(grep -c "def test_" tests/test_mq_core.py) test methods"
echo "  test_mq_consumers.py: $(grep -c "def test_" tests/test_mq_consumers.py) test methods"
echo ""

echo "🔍 Test Classes:"
grep "^class Test" tests/test_mq_core.py tests/test_mq_consumers.py
echo ""

echo "✅ Syntax Check:"
python3 -m py_compile tests/test_mq_core.py && echo "  ✓ test_mq_core.py"
python3 -m py_compile tests/test_mq_consumers.py && echo "  ✓ test_mq_consumers.py"
echo ""

echo "📦 Dependencies:"
grep -E "^(pytest|pydantic|pika)" socket.requirements.txt
echo ""

echo "🎯 Coverage Targets:"
echo "  Line Coverage:   90%+"
echo "  Branch Coverage: 85%+"
echo ""

echo "🚀 To run tests:"
echo "  docker build -t sockets-test ."
echo "  docker run --rm sockets-test pytest tests/ -v"
