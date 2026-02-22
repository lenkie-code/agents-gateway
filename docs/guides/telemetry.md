# Telemetry

Agent Gateway integrates with [OpenTelemetry](https://opentelemetry.io/) to emit distributed traces and metrics from your agent service. This lets you observe agent executions, tool calls, LLM requests, and more using any OpenTelemetry-compatible backend.

## Configuration

Add a `telemetry` block to your `gateway.yaml`:

```yaml
telemetry:
  enabled: true
  service_name: "agent-gateway"
  exporter: "console"       # console | otlp | none
  endpoint: "http://localhost:4317"
  protocol: "grpc"          # grpc | http
  sample_rate: 1.0
```

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Master switch. Set to `true` to activate telemetry. |
| `service_name` | `"agent-gateway"` | The `service.name` resource attribute attached to all spans and metrics. |
| `exporter` | `"console"` | Which exporter to use. See [Exporters](#exporters) below. |
| `endpoint` | `"http://localhost:4317"` | OTLP collector endpoint. Only used when `exporter: otlp`. |
| `protocol` | `"grpc"` | Transport protocol for OTLP. Either `grpc` or `http`. |
| `sample_rate` | `1.0` | Fraction of traces to sample. `1.0` samples everything; `0.1` samples 10%. |

## Exporters

### `console` (default)

Prints span and metric data to stdout. Useful during local development to verify instrumentation without running a collector.

```yaml
telemetry:
  enabled: true
  exporter: "console"
```

### `otlp`

Sends traces and metrics to an OpenTelemetry collector over gRPC or HTTP. Requires the optional OTLP dependencies:

```bash
pip install agents-gateway[otlp]
```

```yaml
telemetry:
  enabled: true
  exporter: "otlp"
  endpoint: "http://localhost:4317"
  protocol: "grpc"
```

### `none`

Disables export entirely. The OpenTelemetry SDK is still initialized (so instrumentation code runs without errors), but no data leaves the process. Use this when you want telemetry APIs available in tests without side effects.

```yaml
telemetry:
  enabled: true
  exporter: "none"
```

## Environment Variable Override

The `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable overrides the `endpoint` value in `gateway.yaml`. This is useful for injecting the collector address at deploy time without changing configuration files:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

Standard OpenTelemetry environment variables such as `OTEL_SERVICE_NAME` and `OTEL_TRACES_SAMPLER` are also respected where applicable.

## What Gets Instrumented

When telemetry is enabled, Agent Gateway configures both a `TracerProvider` and a `MeterProvider` and registers them as the global OpenTelemetry providers. Spans are emitted for:

- Incoming HTTP requests (via FastAPI/Starlette instrumentation)
- Agent invocations and their full execution lifecycle
- Individual tool and skill calls
- LLM requests and responses (including token counts as span attributes)
- Queue operations (enqueue, dequeue, processing)
- Scheduled job runs

Metrics include request counts, latency histograms, and token usage counters.

## Error Handling

Telemetry setup is best-effort. If initialization fails for any reason — missing dependencies, unreachable collector, misconfiguration — Agent Gateway logs a warning and continues running without telemetry. It will never raise an exception or prevent your service from starting.

## Example: Jaeger

Run Jaeger locally with its all-in-one Docker image, which exposes an OTLP gRPC endpoint on port 4317:

```bash
docker run --rm -p 16686:16686 -p 4317:4317 \
  jaegertracing/all-in-one:latest \
  --collector.otlp.enabled=true
```

Configure Agent Gateway to send traces to it:

```yaml
telemetry:
  enabled: true
  exporter: "otlp"
  endpoint: "http://localhost:4317"
  protocol: "grpc"
  service_name: "my-agent-service"
```

Open `http://localhost:16686` in your browser and search for the `my-agent-service` service to see traces.

## Example: Grafana / OpenTelemetry Collector

With a Grafana stack (Tempo for traces, Prometheus for metrics), point your OTLP exporter at the collector:

```yaml
telemetry:
  enabled: true
  exporter: "otlp"
  endpoint: "http://otel-collector:4317"
  protocol: "grpc"
  service_name: "agent-gateway"
  sample_rate: 0.2   # sample 20% in production
```

Alternatively, set the endpoint via environment variable and keep `gateway.yaml` environment-agnostic:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

```yaml
telemetry:
  enabled: true
  exporter: "otlp"
  protocol: "grpc"
```
