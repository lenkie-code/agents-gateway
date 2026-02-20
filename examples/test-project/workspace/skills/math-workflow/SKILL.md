---
name: math-workflow
description: Multi-step arithmetic workflow with automated pipeline
tools:
  - add-numbers
steps:
  - name: first-add
    tool: add-numbers
    input:
      a: "$.input.a"
      b: "$.input.b"

  - name: second-add
    tool: add-numbers
    input:
      a: "$.steps.first-add.output.result"
      b: "$.input.c"

  - name: summarize
    prompt: "Explain the arithmetic result in a clear sentence."
    input:
      first_result: "$.steps.first-add.output"
      final_result: "$.steps.second-add.output"
---

# Math Workflow

A demonstration workflow that chains two additions and summarizes the result.

Given three numbers (a, b, c), it:
1. Adds a + b
2. Adds the result + c
3. Summarizes the chain with an LLM prompt
