"""Lenkie agents-gateway — local dev entry point."""

import os

from dotenv import load_dotenv

from agent_gateway import Gateway

load_dotenv()

gw = Gateway(
    workspace="./workspace",
    title="Lenkie Agent Gateway",
    description="Lenkie's AI agent platform — local dev.",
    version="0.1.0",
)

gw.use_api_keys(
    [
        {
            "name": "dev",
            "key": "dev-api-key",
            "scopes": ["*"],
        }
    ]
)

# Webhook endpoint for agent completion callbacks.
# Set CORE_API_URL to the working-capital-api base URL (defaults to localhost for local dev).
_core_api_url = os.getenv("CORE_API_URL", "http://localhost:8001")
gw.use_webhook_notifications(
    url=f"{_core_api_url}/agents-gateway-webhooks/events",
    name="core-api",
    allow_private_networks=True,  # disable SSRF protection for local dev
)

# Route async agent jobs to RabbitMQ so Celery workers consume them in parallel.
# Celery workers are started separately via: celery -A worker worker -l info --pool=solo
_celery_broker = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672/")
gw.use_celery_queue(broker_url=_celery_broker)

if __name__ == "__main__":
    gw.run(port=9001)
