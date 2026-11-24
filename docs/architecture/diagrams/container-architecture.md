# C4 container view

[Architecture index](../README.md) · [Components](components.md) · [Deployment](deployment.md)

```mermaid
C4Container
  Person(student, "Student", "Uses the web application.")
  System_Boundary(queezo, "Queezo application") {
    Container(browser, "Browser application", "Vue 3 / Vue Router", "Renders pages and study flows. Runs the Pomodoro clock and local state.")
    Container(nginx, "frontend", "Nginx", "Serves built SPA assets and proxies same-origin HTTP and WebSockets.")
    Container(api, "backend", "FastAPI / Uvicorn", "Auth, profiles, decks, study, rooms, and background preparation.")
    Container(gwa, "gwa", "FastAPI / Uvicorn", "Validates the browser session and calculates weighted grades.")
    ContainerDb(db, "Queezo database", "SQLite on named volume", "Stores accounts, decks, cache, solo study, and room state.")
  }
  System_Ext(ollama, "Ollama", "Configured inference endpoint.")
  Rel(student, browser, "Uses")
  Rel(browser, nginx, "Loads assets, sends API requests and room subscriptions", "HTTP(S) / WS(S)")
  Rel(nginx, api, "Proxies application API and room sockets", "HTTP / WebSocket")
  Rel(nginx, gwa, "Proxies calculator requests", "HTTP")
  Rel(api, db, "Reads, writes, and migrates", "SQLAlchemy / SQLite")
  Rel(gwa, db, "Reads authenticated session and user", "SQLAlchemy / SQLite")
  Rel(api, ollama, "Generates candidates on authorized cache miss", "HTTP JSON")
```

The browser handles untrusted entry points. Nginx is the default proxy trusted by private API listeners. Both API services open the same SQLite file on the mounted volume. Ollama sees card text only when the preparation path calls it. Development HMR and the optional backup overlay are shown in [deployment](deployment.md).

Sources [frontend entrypoint](../../../frontend/src/main.js), [Compose](../../../compose.yaml), [Nginx routing](../../../nginx/nginx.conf), [GWA entrypoint](../../../backend/app/gwa/main.py), [generator](../../../backend/app/services/distractors.py).
