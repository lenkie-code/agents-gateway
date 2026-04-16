---
name: deep-research
description: >
  Performs autonomous deep web research on a given topic using Google's deep research
  agent. The agent formulates its own search queries, browses multiple sources, and
  synthesises a comprehensive report. Use this when you need thorough, multi-source
  research rather than a single search result. Returns a detailed research report as text.
parameters:
  prompt:
    type: string
    description: >
      A clear description of what to research. Be specific — include company name,
      registration number, or other identifiers. Example:
      "Find the trading name and official website for UK company 'ACME WIDGETS (UK) LIMITED',
      Companies House number 12345678."
    required: true
  timeout_seconds:
    type: integer
    description: >
      Maximum seconds to wait for the research to complete. Defaults to 120.
      Deep research typically takes 30–90 seconds.
    required: false
---

# Deep Research Tool

Runs an autonomous deep research agent (Google deep-research-pro) that searches
the web, reads multiple pages, and returns a synthesised report.

## When to use

- Research a company to find its trading name, website, or key personnel
- Gather background information that requires reading multiple sources
- Any task where a single search query is insufficient

## Output

Returns a `report` string containing the full synthesised research report.
Returns an `error` string if the research fails or times out.

## Notes

- Research typically completes in 30–90 seconds
- The agent autonomously decides which sources to consult
- Results are based on live web content, not training data
