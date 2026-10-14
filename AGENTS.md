This file provides guidance for AI agents working with this codebase.

# Repository Overview

This repository contains documentation and scripts to aid in deploying the Guardian Connector software stack.
The stack is a suite of different apps, each deployed using CapRover. It can be deployed on the hosting platform of your choice; we provide explicit guidance for Digital Ocean or Azure.


## Project Structure:

Most work happens in:

- `caprover/gc-stack-deploy`: Python package (`src/gc_stack_deploy/stack_deploy.py`, with `example_configs/stack.example.yaml`) to deploy the app stack on an existing CapRover installation
- `caprover/one-click-apps/v4/apps`: a custom repository of caprover apps, built and published by CI

Other folders:

- `azure`: ARM template to deploy VM and storage on Azure
- `digitalocean`: just a README on how to deploy CapRover with a DO Droplet
- `auth0`: just a README
- `warehouse`: just a README on how data is stored and organized in the data warehouse

## Testing and Formatting

- Run the `gc-stack-deploy` unit tests with `make -C caprover/tests test-unit` (this is what CI runs).
- Lint and format Python with Ruff, and write docstrings in NumPy style. See [CONTRIBUTING.md](CONTRIBUTING.md).

# Behavioral Guidelines

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Strong success criteria let you loop independently.

## 5. Write prose for humans

Write docs, READMEs, specs, and code comments for a reader who wasn't in this conversation and is reading months from now.

- Describe how the system works today. Omit history, changes, decision records, and anything that only makes sense next to this conversation or diff ("now returns", "changes", "new"). Name the thing itself in context of its goal.
- Use names and words the user and the codebase already use. Don't use synonyms for something that already has a name.
- Write complete, clear statements, not headlines. Say what does what.
