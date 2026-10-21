# Contributing Guidelines

This repository uses the same contributing guidelines defined in `ConservationMetrics/gc-scripts-hub`:
- [`ConservationMetrics/gc-scripts-hub/CONTRIBUTING.md`](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/CONTRIBUTING.md)
- [`ConservationMetrics/gc-scripts-hub/CONTRIBUTING_EXAMPLES.md`](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/CONTRIBUTING_EXAMPLES.md)
- [`ConservationMetrics/gc-scripts-hub/CONTRIBUTING_LLM_GUIDELINES.md`](https://github.com/ConservationMetrics/gc-scripts-hub/blob/main/CONTRIBUTING_LLM_GUIDELINES.md)

Please review those before submitting pull requests or issues.

Any additional or overriding rules specific to this repository are listed below.


# Contributor License Agreement

By submitting a pull request to this project, you agree to license your contribution under the terms of the [MIT License](/LICENSE).  Make sure that you have the right to license the code under the MIT License and that your contributions do not infringe on the rights of others.


# Contributing & Documentation Style

## Ruff for Python

All developers are expected to use [Ruff](https://github.com/astral-sh/ruff) to lint and format
their Python code. Ruff is a fast, all-in-one Python linter and formatter that ensures consistency
and code quality across the project.

First install Ruff:

    pip install ruff

Configuration lives in [`.ruff.toml`](.ruff.toml)

Developers can choose when in their workflow to apply Ruff formatting and linting. Common choices are as a pre-commit hook or format-on-save.

> You may set up Ruff as a pre-commit hook, to automatically run on all staged Python files before each commit:
>
> 1. `.pre-commit-config.yaml` is already defined at the top of the repo.
> 2. Install the pre-commit package: `pip install pre-commit`
> 3. Install the git hook: `pre-commit install`
>
> Or you may configure your text editor to lint and format on save:
>
> - For VS Code,
>   1. Install the "Ruff" extension
>   2. Add the following to your `settings.json`:
>      ```
>      "[python]": {
>          "editor.formatOnSave": true,
>          "editor.codeActionsOnSave": {
>              "source.fixAll": "explicit",
>              "source.organizeImports": "explicit"
>          },
>          "editor.defaultFormatter": "charliermarsh.ruff"
>      }
>      ```

Document Python code according to **[NumPy's documentation standard](https://numpydoc.readthedocs.io/en/latest/format.html#docstring-standard)**.
