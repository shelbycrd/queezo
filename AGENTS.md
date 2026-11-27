# Queezo — Agent Instructions

## Project
Queezo is a student productivity and learning platform.

THEME: Pastel Blue

Current applications:
- App 1: Flashcards
- App 2: GWA Calculator
- App 3: Pomodoro Timer

The project also includes authentication functionality.

## Working Rules
- Inspect relevant existing code before modifying it.
- Follow the current project architecture and conventions.
- Make minimal, targeted changes.
- Preserve unrelated features and existing UI behavior.
- Do not invent APIs, dependencies, or database schemas.
- Never expose credentials, secrets, or sensitive user data.
- Ask before making destructive or irreversible changes.

## Documentation
- Use README.md for general project information when available.
- Treat source code as the authority for current implementation.
- Read additional project documentation only when relevant.
- Do not assume that external Obsidian notes are accessible.
- For tasks requiring project background, read docs/PROJECT_CONTEXT.md.
- Read only additional documentation relevant to the task. Do not assume the context document is newer than the source code.

## Verification
- Run relevant existing tests when available.
- Report any tests that could not be executed.
- Summarize modified files and important decisions.
- Do not claim functionality works without verification.

## Context Efficiency
- Start with this file and the relevant project files.
- Avoid scanning unrelated directories unnecessarily.
- Retrieve additional documentation only when needed.
- Prioritize correctness over minimizing token usage. (PRIORITY)

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. When the answer is under a Markdown heading, `graphify section "<heading>"` prints that section's text, so the .md need not be opened. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
