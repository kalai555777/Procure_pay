# Clearbuy

A procure-to-pay backend where AI agents do the checking, chasing, and preparing, and people make every decision.

Clearbuy runs a company's purchase journey, from an employee's request to the payment approval request and the renewal a year later. The first release handles software subscriptions for buying companies in the United States. Vendors reach it by email only.

## What it never does

- It never pays, never approves, and never negotiates.
- It never sees bank details.

## How it's built (planned)

| Part | Choice |
| --- | --- |
| Language and API | Python, FastAPI |
| Agent workflow | LangGraph, with checkpoints in PostgreSQL |
| Cloud | AWS: ECS on Fargate (ARM), RDS for PostgreSQL, SQS, KMS, Cognito |
| Infrastructure as code | AWS CDK in Python |
| CI/CD | GitHub Actions, deploying through OIDC (no stored AWS keys) |

It follows ASRA, my own technology-agnostic reference architecture for agentic systems.

## Status

**M1: walking skeleton (in progress).** So far: the project setup and a health route. Next: CI building and testing the ARM container image.

## Run locally

Needs [uv](https://docs.astral.sh/uv/).

```
uv run fastapi dev src/procure_pay/main.py
```

Then open http://127.0.0.1:8000/health