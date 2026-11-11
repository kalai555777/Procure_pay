# Clearbuy: instructions for AI coding tools

This repository (Procure_pay) is Clearbuy, a procure-to-pay agentic backend.
Agents check, chase, and prepare; people make every decision. Clearbuy never
pays, never approves, never negotiates, and never sees bank details.

## Where the design lives

The design is the Clearbuy document, which is not in this repository. Each
task is a GitHub issue that names its piece of Clearbuy Chapter 19.5. If you
need a section of the design, ask the owner to paste it. Do not guess it.
Current milestone: M1, the walking skeleton on AWS (Chapter 19.5).

## Rules for every AI tool (Clearbuy 19.4, AD-264)

1. Write only code the owner can understand and explain. Keep it simple.
2. Small tasks: one issue per branch (issue-N), each with its test.
3. The owner reads every diff. Never change a test just to make it pass;
   say so if a test seems wrong.
4. Ask before running any shell command.
5. Use test-account credentials only, never live ones.
6. No secrets in the repository or in chat: no keys, tokens, passwords,
   or .env files.
7. Before adding a dependency, check that it exists on PyPI and is the right
   package. Add it only with `uv add`; never edit uv.lock by hand.
8. One fresh session per task.

## Quality rules, checked by pre-commit and CI (Clearbuy 19.2, AD-268)

- Style and lint: Ruff, with the rules in pyproject.toml. Functions stay
  simple (complexity 10 or less).
- Types: mypy in strict mode on all of src and tests, with the Pydantic
  plugin. Never loosen strict mode. A third-party library without type
  information gets a per-module `ignore_missing_imports` override only.
  If editor hints disagree with mypy, CI is the judge.
- Tests: every "done when" has a test; coverage stays at 80% or more.
  Never write tests only to raise the number.
- Security: Ruff's security rules; gitleaks for secrets. Never switch off
  row-level security, use a `*` permission, or open a port to make a test pass.
- Dependencies: uv with a lock file. uv only uses versions at least 7 days
  old (`exclude-newer` in pyproject.toml). An `exclude-newer-package`
  exception is only for a real security fix, with the reason in the pull
  request.

## Before saying a task is done, run

    uv lock --check
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy
    uv run pytest

## Never

- Commit or push to main directly. Every change goes through a pull request.
- Skip the hooks (`git commit --no-verify`) or switch off a check.
