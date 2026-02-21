---
title: "Chat Schema Intelligence — Natural Conversation with Schema Agents"
type: feat
status: active
date: 2026-02-21
---

# Chat Schema Intelligence — Natural Conversation with Schema Agents

## Overview

Two changes to the dashboard chat experience:

1. **Schema intelligence**: When chatting with agents that have `input_schema`, the LLM should naturally collect required information through conversation rather than demanding exact field values. API invoke continues to enforce strict schema validation. The agent's own instructions (AGENT.md) decide what to do once all data is gathered.

2. **SSE streaming**: Dashboard chat should stream responses via Server-Sent Events instead of waiting for the full response. Tokens appear progressively in the message bubble as the LLM generates them.

## Problem Statement

The travel-planner agent has `input_schema` with fields like `destination`, `origin`, `departure_date` (YYYY-MM-DD), `nights`, `budget_usd`. When a user says "I want to go to Paris, leaving tomorrow" in chat, the agent rigidly asks for each field in its exact format instead of understanding natural language.

**Root cause**: In the chat flow, the system prompt assembled by `assemble_system_prompt()` does not mention the input schema at all. The executor at `src/agent_gateway/engine/executor.py:169-181` only injects input data when `message_history is None` (invoke flow). For chat, `message_history` is always provided, so the schema is invisible to the LLM.

Additionally, `session.metadata` (where chat input is stored) is passed to `engine.execute()` but never surfaced in the prompt for chat flows — a silent data loss bug.

## Proposed Solution

Inject the agent's `input_schema` into the system prompt with instructions for natural data collection during chat. Keep API invoke validation unchanged.

### 1. Schema-Aware System Prompt Layer

Add a new layer to `assemble_system_prompt()` between the agent prompt and skills section. This layer is **only added when called from a chat context** (new parameter).

#### Prompt Assembly Change

In `src/agent_gateway/workspace/prompt.py`, add parameter `chat_mode: bool = False`:

```python
async def assemble_system_prompt(
    agent: AgentDefinition,
    workspace: WorkspaceState,
    *,
    query: str = "",
    retriever_registry: RetrieverRegistry | None = None,
    context_retrieval_config: ContextRetrievalConfig | None = None,
    memory_block: str = "",
    chat_mode: bool = False,  # NEW
) -> str:
```

After layer 4 (agent behavior) and before layer 5 (memory), add:

```python
# 4.5. Chat schema guidance (only in chat mode)
if chat_mode and agent.input_schema:
    schema_section = _format_chat_schema_guidance(agent.input_schema)
    parts.append(schema_section)
```

#### Schema Guidance Formatter

New function in `prompt.py`:

```python
def _format_chat_schema_guidance(schema: dict[str, Any]) -> str:
    """Format input schema as natural conversation guidance for chat mode."""
    parts = ["## Conversation Data Collection\n"]
    parts.append(
        "This agent accepts structured input. In conversation, you should "
        "naturally gather the following information from the user. Do NOT "
        "ask for each field one by one like a form — have a natural conversation "
        "and extract values from what the user says.\n"
    )

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    if properties:
        parts.append("### Information to collect\n")
        for name, prop in properties.items():
            req_marker = " **(required)**" if name in required else " *(optional)*"
            desc = prop.get("description", "")
            ptype = prop.get("type", "")
            line = f"- **{name}**{req_marker}"
            if desc:
                line += f": {desc}"
            if ptype:
                line += f" (type: {ptype})"
            parts.append(line)

    parts.append("\n### Guidelines\n")
    parts.append(
        "- Interpret natural language values (e.g. 'tomorrow' → actual date, "
        "'about a thousand' → 1000)\n"
        "- Use the current date/time provided above to resolve relative dates\n"
        "- Only ask about optional fields if the user brings them up or they're "
        "contextually relevant\n"
        "- If the user provides multiple values at once, acknowledge them all\n"
        "- Do NOT output raw JSON or field names to the user\n"
        "- Once you have all required information, proceed according to your "
        "instructions — do not ask the user to confirm field-by-field"
    )

    return "\n".join(parts)
```

### 2. Pass `chat_mode=True` in Chat Flows

#### `gateway.py` — `chat()` method

At `src/agent_gateway/gateway.py`, in the `chat()` method where `assemble_system_prompt()` is called, add `chat_mode=True`.

#### `api/routes/chat.py` — streaming path

The streaming SSE handler at `src/agent_gateway/api/routes/chat.py` calls `assemble_system_prompt()` directly. Add `chat_mode=True` there as well.

### 3. Fix Silent Metadata Loss in Chat

Currently `gw.chat()` passes `input=session.metadata` to `engine.execute()`, but the executor skips injection because `message_history is not None`.

**Fix**: In the executor, when `message_history` is provided AND `input` is provided AND `agent.input_schema` exists, append the input values as an additional system-level note so the LLM can see pre-provided data:

```python
# In executor.execute(), after building messages from message_history:
if message_history is not None:
    messages = list(message_history)
    # Surface any pre-provided input data (from API chat callers)
    if input and agent.input_schema:
        input_note = (
            "The caller has pre-provided some input values:\n"
            f"```json\n{json.dumps(input, indent=2)}\n```\n"
            "Use these values and only ask for missing required fields."
        )
        # Append as a system message after the existing system prompt
        messages.insert(1, {"role": "user", "content": input_note})
        messages.insert(2, {"role": "assistant", "content": "Understood, I'll use those values."})
```

This is a lightweight fix — the synthetic exchange is only added when the API chat caller explicitly provides `input` data. The dashboard chat never sends `input`, so this path won't trigger from the dashboard.

### 4. Dashboard Chat SSE Streaming

The dashboard chat currently uses HTMX form POST → waits for full `gw.chat()` response → swaps in an HTML partial. This should be replaced with SSE streaming so tokens appear progressively.

#### New Dashboard Streaming Route

Replace the current `POST /dashboard/chat/send` (which returns a complete HTML partial) with a streaming endpoint:

```python
@protected.post("/dashboard/chat/stream")
async def chat_stream(
    request: Request,
    agent_id: str = Form(...),
    message: str = Form(...),
    session_id: str = Form(""),
    current_user: DashboardUser = Depends(get_dashboard_user),
) -> StreamingResponse:
    """SSE streaming endpoint for dashboard chat."""
```

This route reuses the existing `stream_chat_execution()` engine from `src/agent_gateway/engine/streaming.py`. It:
1. Gets or creates a session (same as current `chat_send`)
2. Assembles the system prompt with `chat_mode=True`
3. Returns a `StreamingResponse` with `media_type="text/event-stream"`
4. Yields SSE events: `token` (text delta), `tool_call`, `tool_result`, `done` (with session_id), `error`

The existing `_create_streaming_response()` in `api/routes/chat.py` is the reference implementation — the dashboard route follows the same pattern but uses form data instead of JSON body and session-cookie auth instead of bearer token.

#### Client-Side: Replace HTMX with EventSource/fetch

The chat form in `app.js` switches from HTMX form submission to a `fetch()` POST that reads the SSE stream. HTMX does not natively support SSE streaming of partial content into an element, so the chat form needs vanilla JS.

```javascript
// Replace HTMX chat form with SSE streaming
async function sendChatMessage(form) {
  const formData = new FormData(form);
  const messagesArea = document.getElementById('messages');

  // Optimistic user bubble (existing behavior)
  appendUserMessage(formData.get('message'));
  form.querySelector('textarea').value = '';

  // Create assistant bubble container
  const bubble = createAssistantBubble();
  messagesArea.appendChild(bubble);
  messagesArea.scrollTop = messagesArea.scrollHeight;

  // Stream response via SSE
  const response = await fetch('/dashboard/chat/stream', {
    method: 'POST',
    body: formData,
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // Parse SSE events from buffer
    const events = parseSSEEvents(buffer);
    buffer = events.remaining;

    for (const event of events.parsed) {
      if (event.type === 'token') {
        fullText += event.data.content;
        bubble.querySelector('.message-bubble').textContent = fullText;
        messagesArea.scrollTop = messagesArea.scrollHeight;
      } else if (event.type === 'done') {
        // Render final markdown, update session_id
        bubble.querySelector('.message-bubble').innerHTML = marked.parse(fullText);
        updateSessionId(event.data.session_id);
      } else if (event.type === 'error') {
        bubble.querySelector('.message-bubble').textContent = event.data.message;
        bubble.classList.add('message-error');
      }
    }
  }
}
```

Key implementation details:
- **No HTMX for chat**: Remove `hx-post`, `hx-target`, `hx-swap` from the chat form. Use a vanilla JS submit handler instead.
- **Progressive rendering**: Update the bubble's `textContent` with each token (fast, no reparse). Only call `marked.parse()` on the final `done` event.
- **SSE parsing**: Simple line-based parser for `event:` and `data:` lines, handling the buffer across chunks.
- **Session tracking**: The `done` event includes `session_id` — store it in a hidden input for subsequent messages.
- **CSRF**: Include the CSRF token in the form data (already present in the hidden input).
- **Error handling**: Network errors and `error` events display in the bubble with error styling.
- **Loading indicator**: Show on send, hide on first `token` event (not on `done`).

#### Chat Template Changes

In `chat.html`:
- Remove HTMX attributes from the chat form (`hx-post`, `hx-target`, `hx-swap`, `hx-indicator`)
- Add `id="chat-form"` and `onsubmit="return false"` (JS handles submission)
- Keep the existing `#messages` container and `#chat-loading` indicator
- The `_chat_message.html` partial is no longer needed for streaming — bubbles are created client-side

#### Existing Non-Streaming Routes

The current `POST /dashboard/chat/send` can be removed (replaced by `/dashboard/chat/stream`). The API's `POST /v1/agents/{id}/chat` with `stream: true` remains unchanged.

### 5. Keep API Invoke Unchanged

No changes to:
- `Gateway.invoke()` — continues to call `validate_input()` strictly
- The executor's invoke path (when `message_history is None`) — continues to inject input as JSON block
- `validate_input()` in `src/agent_gateway/engine/input.py`

### 5. Update Example Project

Update the travel-planner's `AGENT.md` to add behavior guidance for when data is collected:

```markdown
# Travel Planner

You are a travel planning assistant. When you have all the travel details
(destination, origin, dates, budget), call the available tools to build a
comprehensive itinerary. Combine results into a clear travel plan with
sections for Weather, Flights, Hotels, and Activities.
```

Remove the rigid "Use the input fields (destination, origin, departure_date, nights, budget_usd)" instruction — the schema guidance prompt handles field awareness now.

## Technical Considerations

### Architecture

- The schema guidance is a **prompt-only change** — no new API surfaces, no behavioral changes to the engine
- `chat_mode` is a simple boolean flag propagated through existing call paths
- The `_format_chat_schema_guidance()` function reads from `agent.input_schema` which is already a parsed dict

### Date/Time Resolution

The system prompt already includes `Current date and time (UTC): YYYY-MM-DD HH:MM` (prompt.py:47). The schema guidance explicitly tells the LLM to use this for resolving relative dates. The gateway also has a `timezone` config — if set, we should include it in the date/time line so the LLM can resolve "tomorrow" in the operator's timezone rather than UTC.

### History Truncation & Field Loss

When chat history is truncated (default: 100 messages, with tool-call-aware safe truncation), early messages containing user-provided values could be lost. However:
- The schema guidance is in the **system prompt** (never truncated)
- For most conversations, 100 messages is sufficient to collect 5-6 fields
- If this becomes an issue, a future enhancement could track collected fields in `session.metadata`

### Streaming Path

The streaming handler in `api/routes/chat.py` builds its own message list and calls `assemble_system_prompt()`. The `chat_mode=True` parameter must be added there. The streaming handler does NOT go through `gw.chat()`, so it needs the flag independently.

## Acceptance Criteria

### Schema Intelligence
- [ ] `assemble_system_prompt()` accepts `chat_mode` parameter
- [ ] When `chat_mode=True` and agent has `input_schema`, schema guidance section is added to system prompt
- [ ] Schema guidance includes field names, types, descriptions, and required/optional markers
- [ ] Schema guidance instructs LLM to interpret natural language values
- [ ] `gw.chat()` passes `chat_mode=True` to prompt assembly
- [ ] Streaming chat handler passes `chat_mode=True` to prompt assembly
- [ ] Pre-provided `input` data in API chat is surfaced in the message history (metadata fix)
- [ ] API `invoke` flow is completely unchanged (strict validation, JSON injection)
- [ ] Travel-planner example AGENT.md updated with natural conversation instructions
- [ ] Unit test: `assemble_system_prompt(chat_mode=True)` includes schema section
- [ ] Unit test: `assemble_system_prompt(chat_mode=False)` does NOT include schema section
- [ ] Unit test: schema guidance formatting with required/optional fields

### Dashboard SSE Streaming
- [ ] New `POST /dashboard/chat/stream` route returns `StreamingResponse` with `text/event-stream`
- [ ] Route reuses `stream_chat_execution()` from the engine
- [ ] Route passes `chat_mode=True` to prompt assembly
- [ ] Client-side JS reads SSE stream via `fetch()` + `ReadableStream`
- [ ] Tokens appear progressively in the assistant message bubble
- [ ] Final response rendered as markdown (via `marked.js`) on `done` event
- [ ] Session ID from `done` event stored for subsequent messages
- [ ] Error events display with error styling in the bubble
- [ ] Loading indicator shown on send, hidden on first token
- [ ] Old `POST /dashboard/chat/send` route removed
- [ ] HTMX attributes removed from chat form
- [ ] CSRF token included in streaming POST
- [ ] Manual test: chat with any agent shows tokens streaming in real-time

## Success Metrics

- Chat with schema agents feels like a natural conversation, not a form
- Users can say "tomorrow", "about $1000", "3 nights" and the agent understands
- Dashboard chat responses stream progressively — no more waiting for full response
- API invoke with invalid input still returns validation errors
- No regression in non-schema agents' chat behavior

## Files to Create/Modify

### Modified Files
- `src/agent_gateway/workspace/prompt.py` — `chat_mode` param, `_format_chat_schema_guidance()`
- `src/agent_gateway/gateway.py` — pass `chat_mode=True` in `chat()` method
- `src/agent_gateway/api/routes/chat.py` — pass `chat_mode=True` in streaming handler
- `src/agent_gateway/engine/executor.py` — surface pre-provided input in chat message history
- `src/agent_gateway/dashboard/router.py` — replace `chat_send` with `chat_stream` SSE route
- `src/agent_gateway/dashboard/static/dashboard/app.js` — SSE fetch client, replace HTMX chat logic
- `src/agent_gateway/dashboard/templates/dashboard/chat.html` — remove HTMX attrs from chat form
- `examples/test-project/workspace/agents/travel-planner/AGENT.md` — update instructions

### Test Files
- `tests/test_workspace/test_prompt.py` — test `chat_mode` flag and schema guidance formatting
- `tests/test_engine/test_executor.py` — test input surfacing in chat mode
- `tests/test_dashboard/test_chat_stream.py` — test SSE streaming route returns event-stream

## References

- System prompt assembly: `src/agent_gateway/workspace/prompt.py`
- Executor input injection: `src/agent_gateway/engine/executor.py:169-181`
- Chat method: `src/agent_gateway/gateway.py` (chat() method)
- API streaming handler (reference impl): `src/agent_gateway/api/routes/chat.py:120-201`
- SSE engine: `src/agent_gateway/engine/streaming.py`
- Current dashboard chat route: `src/agent_gateway/dashboard/router.py:256-295`
- Dashboard JS: `src/agent_gateway/dashboard/static/dashboard/app.js`
- Travel planner schema: `examples/test-project/workspace/agents/travel-planner/AGENT.md`
- Session store: `src/agent_gateway/chat/session.py`
