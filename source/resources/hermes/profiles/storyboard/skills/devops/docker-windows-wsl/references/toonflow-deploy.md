# Toonflow Deployment Reference

Toonflow is an open-source AI short drama production tool (Apache-2.0 license).

**Repository**: https://github.com/HBAI-Ltd/Toonflow-app

## Quick Deploy to D: Drive

```bash
# Clone to D: drive
cd /mnt/d && mkdir -p Toonflow && cd Toonflow
git clone https://github.com/HBAI-Ltd/Toonflow-app.git
cd Toonflow-app

# Install yarn if not present
npm install -g yarn

# Install dependencies
yarn install

# Build
yarn build

# Start backend service
yarn start
```

## Access

- **URL**: http://localhost:10588/web/index.html
- **Default credentials**: 
  - Username: `admin`
  - Password: `admin123`

## Architecture

Toonflow is a hybrid Electron + Node.js backend app:

- **Backend service** runs on port `10588` (Node.js server)
- **Electron GUI** (optional) can be launched with `yarn dev:gui`
- **Web interface** is accessible via browser at `/web/index.html`

## Build Artifacts

After `yarn build`:
- `build/app.js` — Backend service entry point
- `build/main.js` — Electron main process

## Scripts

| Command | Purpose |
|---------|---------|
| `yarn dev` | Start backend in dev mode with hot reload |
| `yarn dev:gui` | Start Electron GUI in dev mode |
| `yarn start` | Start production backend service |
| `yarn build` | Build backend + Electron main process |
| `yarn dist` | Build + package Electron app for distribution |

## Prerequisites

The app requires API endpoints for:
- Large language model (LLM) service
- Video generation (Sora or Doubao/豆包)
- Image generation (Nano Banana Pro)

Configure these in the web UI after first login.

## Tech Stack

- **TypeScript** + **Node.js**
- **Electron** (desktop wrapper)
- **Vite** (frontend build)
- **better-sqlite3** (local database)
- **AI SDK** (Anthropic, OpenAI, DeepSeek, xAI integrations)

## Deployment Location

Standard deployment path: `D:\Toonflow\Toonflow-app`

This keeps the project on the D: drive (common when C: is low on space) and accessible from both Windows and WSL via `/mnt/d/Toonflow/Toonflow-app`.
