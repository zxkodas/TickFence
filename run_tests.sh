#!/usr/bin/env bash
# Todas las suites, cada una en su propio proceso (test_ui crea un
# QApplication y Qt solo permite uno por proceso).
#   ./run_tests.sh          # todo
#   ./run_tests.sh --quick  # salta test_guard (la lenta)
set -u
cd "$(dirname "$0")"
QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1
SUITES="test_focuslock test_win32 test_imports test_ifeo test_stub test_ui test_extension test_guard test_config test_i18n test_installer"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
FAIL=0
for s in $SUITES; do
  if [ "$QUICK" = 1 ] && [ "$s" = "test_guard" ]; then echo "== $s: skipped (--quick)"; continue; fi
  echo "== $s"
  if ! python3 -m "tests.$s"; then FAIL=1; fi
done
exit "$FAIL"
