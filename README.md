# GOIT CS HW-06 — Minimal Web App (HTTP + UDP + MongoDB)

A tiny, framework-free web app that serves static/html pages, accepts a message via a form, forwards it to a UDP socket server, and stores it in MongoDB. Runs fully in Docker.

## What’s implemented

- HTTP server on **port 3000**:
  - `/` → `templates/index.html`
  - `/message.html` → message form (`username`, `message`)
  - `/static/...` → static assets (CSS/PNG/ICO)
  - unknown paths → `templates/error.html` (404)
- UDP socket server on **port 5000**:
  - receives URL-encoded form data
  - adds server-side timestamp
  - saves to MongoDB collection `messages`
- MongoDB with authentication, data persisted via Docker volume
- Clean PEP 8 Python code, simple routing, safe static serving, basic validation
- Dockerfile + docker-compose for one-command run

## Tech stack

- Python 3.11 (standard lib: `http.server`, `multiprocessing`, `socket`)
- PyMongo
- Docker, Docker Compose
- MongoDB 6

## Project structure

```text
.
├─ static/
│  ├─ favicon.ico
│  ├─ logo.png
│  └─ style.css
├─ templates/
│  ├─ error.html
│  ├─ index.html
│  └─ message.html
├─ docker-compose.yaml
├─ Dockerfile
├─ main.py
├─ requirements.txt
├─ .dockerignore
├─ .gitignore
└─ README.md
```

## How to run

### Prerequisites
- Docker & Docker Compose installed.

### Start the stack
```bash
docker-compose up --build
```

You should see logs like:
- `[HTTP] listening on http://0.0.0.0:3000`
- `[SOCKET] UDP listening on 0.0.0.0:5000`
- `[SOCKET] Connected to MongoDB: mongodb://root:example@mongo:27017/?authSource=admin`

### Open the app
- Home: http://localhost:3000  
- Form: http://localhost:3000/message.html  
- 404 demo: http://localhost:3000/does-not-exist

### Send a quick test (from terminal)
```bash
curl -i -X POST   -d "username=TestUser&message=Hello+from+curl"   http://localhost:3000/submit
```

## Inspect data in MongoDB

**Option A: via container**
```bash
docker compose exec mongo mongosh -u root -p example --authenticationDatabase admin
```
Then in `mongosh`:
```js
use messages_db
show collections
db.messages.countDocuments()
db.messages.find({}, { _id: 0 }).sort({ _id: -1 }).limit(10).pretty()
```

**Option B: from host (Compass / mongosh)**
```
mongodb://root:example@localhost:27017/?authSource=admin
```

## Configuration

Values are provided via `docker-compose.yaml`:

```yaml
environment:
  MONGO_URI: mongodb://root:example@mongo:27017/?authSource=admin
  MONGO_DB: messages_db
  MONGO_COLL: messages
```

Ports:
- `3000:3000` (HTTP) is exposed to host.
- UDP `5000` is internal to the container (not exposed by default). Expose if needed:
  ```yaml
  ports:
    - "3000:3000"
    - "5000:5000/udp"
  ```

## Screenshots

- **Home page**

  ![Home page](screenshots/page-home.png)

- **Message form**

  ![Message form](screenshots/page-messages.png)

- **404 page**

  ![Not Found page](screenshots/page-error.png)

- **MongoDB messages (mongosh)**

  ![Mongo messages](screenshots/messages.png)

---

### Notes

- The server performs basic server-side validation (skips empty fields).  
- Static links in HTML should be absolute, e.g. `/static/style.css`.  
- Favicon: `<link rel="icon" href="/static/favicon.ico">`.  
