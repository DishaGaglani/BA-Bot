# Docker Deployment Instructions

This document describes how to deploy the BA-Bot application using Docker and Docker Compose on a local server.

## Prerequisites

1. **Docker**: Ensure Docker is installed on your local server.
   - [Install Docker](https://docs.docker.com/get-docker/)
2. **Docker Compose**: Usually bundled with Docker Desktop. For Linux servers, ensure the `docker-compose-plugin` or `docker-compose` CLI is installed.

---

## Installation & Startup

### 1. Configure the Environment

Open the `docker-compose.yml` file in the root directory and configure the environment variables under the `backend` service:

- `JWT_SECRET`: Change this to a secure random string (minimum 32 characters) for signing authentication tokens.
- `PREDICTION_URL`: Configured to connect to the live Forjinn Flow prediction API (`https://forjinn.com/...`). Ensure this matches the endpoint for your organization's prediction flow.
- `FRONTEND_URL`: List the IP address or domain name of your local server (comma-separated, e.g. `http://localhost,http://192.168.1.10`) to authorize CORS requests.
- `ports` under `frontend`: If port `80` is already in use by another service on your server, change the mapping (e.g., `"3000:80"` to serve on port `3000`).

### 2. Build and Launch the Application

From the root directory of the project, run the following command to build the Docker images and start the containers in detached (background) mode:

```bash
docker compose up --build -d
```

This will:
- Download the necessary base images (Node, Python, Nginx).
- Compile the frontend assets and serve them inside the Nginx container.
- Launch the FastAPI backend container.
- Seed the SQLite database schemas and default roles/users automatically.

### 3. Verify the Deployment

1. Check the running containers:
   ```bash
   docker compose ps
   ```
2. View backend application logs to verify everything started successfully:
   ```bash
   docker compose logs -f backend
   ```
3. Open your browser and navigate to `http://localhost` (or `http://<server-ip>`). The application interface should load, allowing you to register, log in, and create workspaces.

---

## Data Persistence & Volumes

To ensure your projects, users, configurations, and generated document reports are not lost when the containers are stopped or updated, two Docker volumes are automatically created:

1. **`backend-data`**: Persists the SQLite database file (`ba_bot.db`).
2. **`backend-uploads`**: Persists generated DOCX/PDF reports and other file uploads.

These volumes persist across container updates. If you ever need to inspect or back up the database directly on the host, Docker stores local volumes under `/var/lib/docker/volumes/`.

---

## Stopping or Restarting the App

- **To stop the application**:
  ```bash
  docker compose down
  ```
- **To restart the application**:
  ```bash
  docker compose restart
  ```
- **To view logs for all services**:
  ```bash
  docker compose logs -f
  ```
