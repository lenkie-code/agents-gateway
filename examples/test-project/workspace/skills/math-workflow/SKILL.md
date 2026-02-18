---
name: math-workflow
description: Multi-step arithmetic workflow for testing
tools:
  - add-numbers
---

# Math Workflow

When asked to perform multi-step arithmetic:

1. Break the problem into individual addition operations
2. Use `add_numbers` for each step
3. Combine results and present the final answer

## Example

"What is 1 + 2 + 3?"
- Step 1: add_numbers(1, 2) = 3
- Step 2: add_numbers(3, 3) = 6
- Answer: 6
