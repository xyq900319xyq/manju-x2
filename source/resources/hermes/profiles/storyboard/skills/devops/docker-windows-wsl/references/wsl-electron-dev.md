# WSL Electron Development Setup

Running Electron apps in WSL requires X server support and system libraries.

## Prerequisites

### 1. Check for WSLg (Windows 11 built-in X server)

```bash
ls /mnt/wslg 2>&1 && echo "WSLg available" || echo "WSLg not available"
```

If WSLg is available, you only need to set `DISPLAY=:0`.

### 2. Install Electron dependencies

```bash
sudo apt-get update && sudo apt-get install -y \
  libnss3 \
  libatk1.0-0t64 \
  libatk-bridge2.0-0t64 \
  libcups2t64 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2t64
```

**Note**: Ubuntu 25.04+ uses `t64` suffixed packages (time64 transition). Older versions use the non-suffixed names.

### 3. Install Chinese fonts (if UI shows squares)

```bash
sudo apt-get install -y fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei
```

After installing fonts, restart the Electron app.

## Running Electron in dev mode

```bash
export DISPLAY=:0
cd /path/to/electron-project
npm run dev
```

## Common Errors

### `Missing X server or $DISPLAY`

**Cause**: DISPLAY environment variable not set or X server not running.

**Fix**: 
```bash
export DISPLAY=:0
```

Add to `~/.bashrc` for persistence:
```bash
echo 'export DISPLAY=:0' >> ~/.bashrc
```

### `error while loading shared libraries: libnss3.so`

**Cause**: Missing Electron runtime dependencies.

**Fix**: Install the full dependency list above (step 2).

### All text shows as squares

**Cause**: Missing Chinese/CJK fonts.

**Fix**: Install fonts (step 3) and restart the app.

## Deployment Pattern: Dual Version Strategy

When working with Electron apps on Windows + WSL:

1. **Prebuilt Windows version** (`/mnt/d/App/win-unpacked/app.exe`) — runs natively on Windows, no X server needed, fonts work out of box.
2. **WSL dev version** (`~/project/`) — requires X server + dependencies, but allows live source editing.

**User preference**: Deploy both. The prebuilt version is the fallback when WSL setup hits blockers.

## Toonflow Deployment Example

```bash
# Clone to D: drive
cd /mnt/d && mkdir -p Toonflow && cd Toonflow
git clone https://github.com/HBAI-Ltd/Toonflow-app.git
cd Toonflow-app

# Install dependencies
npm install -g yarn
yarn install

# Build
yarn build

# Start (backend only, no GUI)
yarn start
# Access at http://localhost:10588/web/index.html
```

**Default credentials**: `admin` / `admin123`

## Autonomous Setup Strategy

When the user says "solve it yourself" and sudo is required:

1. **Provide a single consolidated command** the user can paste once:
   ```bash
   sudo apt-get update && sudo apt-get install -y libnss3 libatk1.0-0t64 ... fonts-noto-cjk
   ```
2. **Proceed with the rest of the workflow** (export DISPLAY, npm run dev) immediately after, don't wait for confirmation.
3. **Don't repeatedly ask** "do you want me to configure X?" — just state what's needed and move forward.

The user's frustration signal ("deepseek比你强一万八千倍") indicates they want **proactive execution**, not **permission-seeking dialogue**.
