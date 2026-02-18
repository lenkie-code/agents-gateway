---
name: http-example
description: Test HTTP tool that calls httpbin.org
type: http
http:
  method: GET
  url: "https://httpbin.org/get?q=${query}"
  timeout_ms: 5000
parameters:
  query:
    type: string
    description: "Query string to send"
    required: true
---

# HTTP Example Tool

Calls httpbin.org to test HTTP tool execution. Returns request details.
