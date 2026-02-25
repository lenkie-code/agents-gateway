# CLI Usage

Agent Gateway ships a command-line interface for inspecting workspaces, invoking
agents, and managing the database.

## Output Formats

The `agents`, `skills`, and `schedules` commands accept a `--format` / `-f` flag
with three options:

| Format | Description |
|--------|-------------|
| `table` | Human-readable table (default) |
| `json` | JSON array — ideal for scripting and piping to `jq` |
| `csv` | CSV with header row — ideal for spreadsheets |

```bash
# List agents as JSON
agents-gateway agents -w workspace --format json

# List skills as CSV
agents-gateway skills -w workspace -f csv

# List schedules as a table (default)
agents-gateway schedules -w workspace
```

### Invoke

The `invoke` command supports `--format table` (default) and `--format json`.
CSV is not supported for invoke output. The legacy `--json` flag is still
accepted but `--format json` is preferred:

```bash
agents-gateway invoke assistant "Hello" -w workspace --format json

# Legacy (still works)
agents-gateway invoke assistant "Hello" -w workspace --json
```

Using both `--json` and `--format` simultaneously is an error.

## Commands

| Command | Description |
|---------|-------------|
| `agents` | List discovered agents |
| `skills` | List discovered skills |
| `schedules` | List discovered schedules |
| `invoke` | Invoke an agent |
| `chat` | Interactive chat session |
| `serve` | Start the HTTP server |
| `check` | Validate workspace configuration |
| `init` | Scaffold a new workspace |
| `db upgrade` | Run database migrations |
| `db downgrade` | Roll back migrations |
| `db current` | Show current migration version |
| `db history` | Show migration history |
| `version` | Show version |
