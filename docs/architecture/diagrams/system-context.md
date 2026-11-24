# C4 system context

[Architecture index](../README.md) · [Containers](container-architecture.md)

```mermaid
C4Context
  Person(student, "Student", "Creates decks, studies alone or in rooms, calculates GWA, and uses Pomodoro.")
  Person(visitor, "Visitor", "Can open a visible profile and the account entry points.")
  Person(operator, "Operator", "Maintains accounts and backups through the deployment and CLI.")
  System(queezo, "Queezo", "Study application with flashcards, collaborative study, GWA, and Pomodoro.")
  System_Ext(ollama, "Ollama", "Runs a configured local model for distractor inference.")
  System_Ext(restic, "Restic repository", "Optional operator-configured off-host backup destination.")
  Rel(student, queezo, "Uses", "Browser HTTP(S) and WebSocket")
  Rel(visitor, queezo, "Browses or signs in", "Browser HTTP(S)")
  Rel(operator, queezo, "Administers", "Compose and CLI")
  Rel(queezo, ollama, "Requests candidate text on cache misses", "HTTP JSON")
  Rel(queezo, restic, "Copies verified snapshots when configured", "Restic")
```

A student may act as a host, participant, or spectator in a particular room. Those roles derive from membership and session history. The operator uses administrative commands without a separate in-app operator role. Ollama and the optional off-host repository are outside the application boundary.

Sources [overview](../01-system-overview.md), [application assembly](../../../backend/app/main.py), [CLI](../../../backend/app/cli.py), [recovery runbook](../../production/DATABASE_RELIABILITY.md).
