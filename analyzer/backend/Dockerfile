FROM python:3.11-slim

WORKDIR /app

# Install packages in dependency order
COPY partenit/packages/core partenit/packages/core
COPY partenit/packages/policy-dsl partenit/packages/policy-dsl
COPY partenit/packages/trust-engine partenit/packages/trust-engine
COPY partenit/packages/agent-guard partenit/packages/agent-guard
COPY partenit/packages/adapters partenit/packages/adapters
COPY partenit/packages/decision-log partenit/packages/decision-log
COPY partenit/packages/safety-bench partenit/packages/safety-bench
COPY analyzer/backend analyzer/backend

RUN pip install --no-cache-dir \
    partenit/packages/core \
    partenit/packages/policy-dsl \
    partenit/packages/trust-engine \
    partenit/packages/agent-guard \
    partenit/packages/adapters \
    partenit/packages/decision-log \
    partenit/packages/safety-bench \
    analyzer/backend \
    && pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8000

CMD ["uvicorn", "partenit.analyzer.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
