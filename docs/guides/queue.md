# Queue

By default, every agent run is synchronous — the HTTP request blocks until the agent finishes. For long-running agents this is impractical. The queue system lets agents run asynchronously: the API returns immediately with a `202 Accepted` and a URL to poll for the result.

## Setting an Agent to Async Mode

In the agent's `AGENT.md` frontmatter:

```yaml
---
name: research-agent
execution_mode: async
---
```

With async mode enabled, `POST /v1/agents/research-agent/chat` returns:

```json
{
  "execution_id": "exec_01abc...",
  "status": "queued",
  "poll_url": "/v1/executions/exec_01abc..."
}
```

Poll `GET /v1/executions/{id}` until `status` is `completed`, `failed`, or `cancelled`.

!!! note
    Async mode requires a queue backend other than `none`. If no queue is configured, the Gateway falls back to synchronous execution regardless of the agent setting.

---

## Backends

### none (default)

No queue. All executions are synchronous. Suitable when all agents are short-lived and you do not need async support.

### memory

In-process `asyncio.Queue`. No external dependencies. Workers and the HTTP server share the same process.

```python
gw.use_memory_queue()
```

**Use only for development and testing.** Queued jobs are lost if the process restarts.

### Redis

Redis Streams-based queue. Durable, supports multiple workers, and survives process restarts.

**Install the extra:**

```bash
pip install agents-gateway[redis]
```

**Configure via `gateway.yaml`:**

```yaml
queue:
  backend: redis
  redis_url: "redis://localhost:6379/0"
  stream_key: "agent_gateway:executions"
  consumer_group: "workers"
```

**Or configure fluently:**

```python
gw.use_redis_queue(
    url="redis://localhost:6379/0",
    stream_key="agent_gateway:executions",
    consumer_group="workers",
)
```

### RabbitMQ

AMQP durable queue. Messages survive broker restarts when the queue is declared durable (the default).

**Install the extra:**

```bash
pip install agents-gateway[rabbitmq]
```

**Configure via `gateway.yaml`:**

```yaml
queue:
  backend: rabbitmq
  rabbitmq_url: "amqp://user:pass@localhost/"
  queue_name: "agent_gateway"
```

**Or configure fluently:**

```python
gw.use_rabbitmq_queue(
    url="amqp://user:pass@localhost/",
    queue_name="agent_gateway",
)
```

---

## Worker Configuration

```yaml
queue:
  workers: 4
  max_retries: 3
  visibility_timeout_s: 300
  drain_timeout_s: 30
```

| Setting | Default | Description |
|---------|---------|-------------|
| `workers` | `4` | Number of concurrent worker coroutines |
| `max_retries` | `3` | Times a job is retried before being marked failed |
| `visibility_timeout_s` | `300` | Seconds a job is hidden from other workers while being processed |
| `drain_timeout_s` | `30` | Seconds to wait for in-flight jobs to finish during shutdown |

---

## Worker-Only Mode

In a multi-process deployment you may want dedicated worker processes that consume the queue without exposing an HTTP server:

```bash
agents-gateway serve --worker-only
```

This starts the queue workers and scheduler (if enabled) but does not bind to a port. Run this alongside your normal Gateway instances to scale processing independently from the API layer.

---

## Polling for Results

```bash
GET /v1/executions/{execution_id}
```

Response fields:

```json
{
  "execution_id": "exec_01abc...",
  "agent": "research-agent",
  "status": "completed",
  "created_at": "2025-10-01T09:00:00Z",
  "completed_at": "2025-10-01T09:00:45Z",
  "output": "..."
}
```

Possible `status` values: `queued`, `running`, `completed`, `failed`, `cancelled`.

---

## Cancellation

Cancel a queued or running execution via the API:

```bash
POST /v1/executions/{execution_id}/cancel
```

Or in code:

```python
await gw.cancel_execution("exec_01abc...")
```

Cancellation is best-effort. A job that has already started may not stop immediately — the agent will finish its current LLM call before checking for a cancellation signal.

---

## Custom Queue Backend

Implement the `ExecutionQueue` protocol to integrate any queue system:

```python
from agent_gateway.queue import ExecutionQueue

class MyQueue(ExecutionQueue):
    async def enqueue(self, job):
        ...

    async def dequeue(self):
        ...

    async def ack(self, job_id):
        ...

    async def nack(self, job_id):
        ...

    async def cancel(self, job_id):
        ...

gw.use_queue(MyQueue())
```

Refer to `agent_gateway.queue.ExecutionQueue` for the full protocol definition.
