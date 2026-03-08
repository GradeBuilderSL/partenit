#!/usr/bin/env bash
# Запуск H1 bridge внутри Isaac Sim.
# Использует ISAAC_SIM_PYTHON, если задан, иначе ищет python.sh в типичных путях.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -n "$ISAAC_SIM_PYTHON" ]]; then
    PYTHON="$ISAAC_SIM_PYTHON"
elif [[ -x "$SCRIPT_DIR/python.sh" ]]; then
    PYTHON="$SCRIPT_DIR/python.sh"
else
    echo "Не найден Python для Isaac Sim."
    echo "Задайте переменную окружения: export ISAAC_SIM_PYTHON=/path/to/isaacsim/.../python.sh"
    echo "Или запустите вручную из этой папки: /path/to/python.sh h1_bridge.py"
    exit 1
fi

echo "Запуск моста: $PYTHON h1_bridge.py"
exec "$PYTHON" h1_bridge.py
