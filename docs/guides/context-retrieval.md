# Context Retrieval

Agent Gateway supports retrieval-augmented generation (RAG) by letting you attach context retrievers to your gateway. Retrieved content is injected into the agent's system prompt at execution time, giving the model access to relevant knowledge without fine-tuning.

## The `ContextRetriever` Protocol

Any object that implements the following protocol can be used as a retriever:

```python
from typing import Protocol

class ContextRetriever(Protocol):
    async def retrieve(self, query: str, agent_id: str) -> list[str]:
        """Return a list of relevant text chunks for the given query."""
        ...

    async def initialize(self) -> None:
        """Called once when the gateway starts up."""
        ...

    async def close(self) -> None:
        """Called once when the gateway shuts down."""
        ...
```

`retrieve` receives the user's input as `query` and the agent's identifier as `agent_id`, so a single retriever can serve multiple agents differently if needed.

## Registering a Retriever

Register retrievers on the gateway before it starts:

```python
from agent_gateway import Gateway

gw = Gateway()
gw.use_retriever("my-kb", MyRetriever())
```

The first argument is the retriever name. You can register multiple retrievers with different names.

## Referencing Retrievers in `AGENT.md`

Tell an agent which retrievers to use in its `AGENT.md` frontmatter:

```markdown
---
name: Support Assistant
retrievers:
  - my-kb
---

You are a helpful support assistant.
```

When the agent is invoked, all listed retrievers are called with the user's query and the results are appended to the system prompt before the LLM receives it.

## Writing a Custom Retriever

Here is a minimal example using a hypothetical vector store client:

```python
from agent_gateway.context import ContextRetriever
from my_vector_store import VectorStoreClient

class KnowledgeBaseRetriever:
    def __init__(self, index_name: str) -> None:
        self._index_name = index_name
        self._client: VectorStoreClient | None = None

    async def initialize(self) -> None:
        self._client = await VectorStoreClient.connect()

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    async def retrieve(self, query: str, agent_id: str) -> list[str]:
        assert self._client is not None
        results = await self._client.search(
            index=self._index_name,
            query=query,
            top_k=5,
        )
        return [r.text for r in results]
```

Register it on your gateway:

```python
gw.use_retriever("support-kb", KnowledgeBaseRetriever("support-docs"))
```

## Configuration

Add a `context_retrieval` block to `gateway.yaml` to tune retrieval behaviour:

```yaml
context_retrieval:
  retriever_timeout_seconds: 10      # Max time to wait for each retriever call
  max_retrieved_chars: 50000         # Max total characters from retriever results
  max_context_file_chars: 100000     # Max total characters from static context files
```

| Field | Default | Description |
|---|---|---|
| `retriever_timeout_seconds` | `10` | If a retriever does not respond within this time, its results are skipped and a warning is logged. |
| `max_retrieved_chars` | `50000` | Retrieved chunks are truncated to stay within this limit before injection. |
| `max_context_file_chars` | `100000` | Static context files are truncated to stay within this limit. |

## Static Context Files

For knowledge that does not change frequently, place Markdown files in the agent's `context/` directory. These are automatically discovered and included in every system prompt for that agent.

```
workspace/
  agents/
    support-assistant/
      AGENT.md
      context/
        product-overview.md
        faq.md
        troubleshooting.md
```

You can also reference specific file paths in the `AGENT.md` frontmatter `context:` list:

```markdown
---
name: Support Assistant
context:
  - context/product-overview.md
  - ../../shared/policies.md
retrievers:
  - my-kb
---
```

> **Note:** Path traversal is protected. Context file paths are resolved relative to the agent's workspace directory and any attempt to escape that directory (e.g. via `../../../etc/passwd`) is rejected with an error.

Both static files and retriever results are combined and injected into the system prompt. Static files are loaded first, followed by retriever results.
