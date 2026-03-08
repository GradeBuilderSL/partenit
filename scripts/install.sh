#!/usr/bin/env bash
# Установка всех пакетов Partenit из исходников (после clone).
# Запускать из корня репозитория.

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "partenit/packages/core" ]]; then
    echo "Запустите скрипт из корня репозитория (где лежит partenit/packages/core)."
    exit 1
fi

echo "Установка пакетов Partenit (editable) из $ROOT ..."

pip install -e partenit/packages/core
pip install -e partenit/packages/policy-dsl
pip install -e partenit/packages/trust-engine
pip install -e partenit/packages/agent-guard
pip install -e partenit/packages/adapters
pip install -e partenit/packages/safety-bench
pip install -e partenit/packages/decision-log

echo "Готово. Проверка:"
python -c "from partenit.agent_guard import GuardedRobot; from partenit.adapters import MockRobotAdapter; print('OK')"
partenit-bench --help > /dev/null && echo "  partenit-bench OK"
partenit-eval --help > /dev/null && echo "  partenit-eval OK"
partenit-log --help > /dev/null && echo "  partenit-log OK"
partenit-policy --help > /dev/null && echo "  partenit-policy OK"
echo "Установка завершена."
