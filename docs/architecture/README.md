# Queezo Software Architecture Document

This guide describes the repository at commit `2e2b636`, reviewed on November 24, 2026. It covers application boundaries, code ownership, persistent state, request flows, and the deployment topology defined in source. Operational and test evidence is identified separately from source-derived behavior.

## Start here

| Chapter | Use it to understand |
| --- | --- |
| [01 · System overview](01-system-overview.md) | Users, applications, technologies, and external boundaries |
| [02 · Architecture and components](02-architecture-and-components.md) | Vue, both APIs, module responsibilities, and error handling |
| [03 · Database design](03-database-design.md) | All tables, keys, deletion rules, schema evolution, and storage |
| [04 · Authentication and security](04-authentication-and-security.md) | Sessions, CSRF, resource authorization, and controls |
| [05 · Flashcards and AI](05-flashcards-and-ai.md) | Editing, Classic, Multiple-Choice, Ollama, and shared cache |
| [06 · Multiplayer Study Rooms](06-multiplayer-study-rooms.md) | Invitations, gameplay, WebSockets, presence, recovery, and scoring |
| [07 · Deployment and infrastructure](07-deployment-and-infrastructure.md) | Compose, proxy, configuration, logs, and backups |
| [08 · Data flows and lifecycle](08-data-flows-and-lifecycle.md) | Message paths, clocks, state ownership, and scenario index |
| [09 · Architecture decisions](09-architecture-decisions.md) | Evidence, inferred rationale, and technical debt |
| [Verification](VERIFICATION.md) | Schema, diagram, link, and test checks |

## Diagram catalog

Mermaid diagrams render in compatible Markdown viewers. PlantUML diagrams include SVG previews followed by their editable source.

- [C4 system context](diagrams/system-context.md) and [C4 containers](diagrams/container-architecture.md)
- [UML components](diagrams/components.md), [domain classes](diagrams/domain-classes.md), and [physical database ER](diagrams/database-er.md)
- UML sequences for [accounts and card editing](diagrams/sequences/accounts-and-cards.md), [solo and AI](diagrams/sequences/solo-and-ai.md), and [Study Rooms](diagrams/sequences/study-rooms.md)
- UML state machines for [rooms, sessions, invitations, and rounds](diagrams/states/study-rooms.md) and [distractor preparation](diagrams/states/distractors.md)
- UML activities for [Multiple-Choice preparation and caching](diagrams/activities/multiple-choice.md) and [room participation and gameplay](diagrams/activities/study-rooms.md)
- [UML deployment views](diagrams/deployment.md)

For operational procedures, use the [project README](../../README.md), [account setup](../../AUTH_SETUP.md), and [database recovery runbook](../production/DATABASE_RELIABILITY.md). The [documentation index](../README.md) links to historical reports and current development guidance. Code references in the chapters take precedence when behavior differs.
