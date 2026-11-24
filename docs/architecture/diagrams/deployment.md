# UML deployment

[Architecture index](../README.md) · [Infrastructure](../07-deployment-and-infrastructure.md)

## Base Compose

![Base Docker topology with Nginx, APIs, SQLite and Ollama](rendered/base-compose.svg)

```plantuml
@startuml
left to right direction
node "Browser / operator machine" as Client
node "Docker host" {
  node "Ollama dependency\nDefault host port 11434" as Ollama
  node "Compose bridge" {
    node "frontend container\nNginx port 80" as Front {
      artifact "Built Vue assets" as Assets
    }
    node "backend container\nUvicorn port 8000" as Back {
      artifact "app.main:app" as Api
    }
    node "gwa container\nUvicorn port 8000" as Calc {
      artifact "app.gwa.main:app" as Gwa
    }
  }
  database "queezo_data volume\n/data/queezo.db" as Data
}
Client --> Front : Default host loopback 8080\nHTTP and WS
Front --> Back : /api/ and room sockets
Front --> Calc : /api/gwa/ and /gwa/
Back --> Data : SQLite read / write
Calc --> Data : SQLite session reads
Back --> Ollama : HTTP /api/chat\nDefault host.docker.internal
@enduml
```

Base Compose publishes Nginx on loopback. The backend and GWA ports are bridge-only. A deployment may terminate public HTTPS upstream. Neither that gateway nor a hosted instance is defined by the repository.

Sources [Compose](../../../compose.yaml), [frontend image](../../../nginx/Dockerfile), [backend image](../../../backend/Dockerfile), [Nginx config](../../../nginx/nginx.conf).

## Optional overlays

![Optional Vite development and backup deployments](rendered/compose-overlays.svg)

```plantuml
@startuml
left to right direction
node "Developer browser" as Browser
node "Docker host" {
  folder "Frontend working tree" as Source
  node "frontend-dev container\nVite and HMR" as Dev
  node "frontend container\nBase Nginx proxy" as Front
  node "backup container\nScheduled backup process" as Backup
  database "frontend_dev_node_modules" as Modules
  database "queezo_data" as Data
  database "queezo_backups" as Backups
}
cloud "Optional Restic repository" as Restic
Browser --> Dev : localhost:5173 / HTTP and HMR
Dev --> Front : API HTTP and WebSocket proxy
Dev --> Source : /app bind mount
Dev --> Modules : Node dependencies
Backup --> Data : /data read-only
Backup --> Backups : /backups snapshot writes
Backup --> Restic : optional off-host copy
@enduml
```

Development and backup are independent overlays. Development augments local-origin policy for both APIs. Backup stores SQLite snapshots on a separate volume and can copy them to an externally configured repository.

Sources [development overlay](../../../compose.dev.yaml), [Vite proxy](../../../frontend/vite.config.js), [backup overlay](../../../compose.backup.yaml), [runbook](../../production/DATABASE_RELIABILITY.md).
