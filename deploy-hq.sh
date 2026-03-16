#!/bin/bash
# Deploy HypeCheck to wisechef-hq
# Run from local machine (adam-xps)
set -e

HQ="wisechef@77.42.92.141"
REMOTE_DIR="/home/wisechef/companies/wisechef/hypecheck"

echo "📦 Syncing hypecheck to wisechef-hq..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '*.egg-info' --exclude '.pytest_cache' \
  ~/repos/hypecheck/ $HQ:$REMOTE_DIR/

echo "🐍 Setting up Python venv + deps..."
ssh $HQ "cd $REMOTE_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]' && pip install fastapi 'uvicorn[standard]' 2>&1 | tail -5"

echo "🔑 Setting env vars..."
ssh $HQ "cd $REMOTE_DIR && cat > .env << 'EOF'
OPENAI_API_KEY=$(grep OPENAI_API_KEY ~/clawd/.env | cut -d= -f2-)
HYPECHECK_API_KEYS=hc_demo_key_2026
HYPECHECK_REPORT_DIR=/home/wisechef/companies/wisechef/hypecheck/.hypecheck/reports
EOF"

echo "🚀 Creating systemd service..."
ssh $HQ "cat > /tmp/hypecheck-api.service << 'UNIT'
[Unit]
Description=HypeCheck API
After=network.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_DIR
Environment=PATH=$REMOTE_DIR/.venv/bin:/usr/bin
EnvironmentFile=$REMOTE_DIR/.env
ExecStartPre=/usr/bin/fuser -k 3347/tcp || true
ExecStart=$REMOTE_DIR/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 3347
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
mkdir -p ~/.config/systemd/user/
cp /tmp/hypecheck-api.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable hypecheck-api
systemctl --user restart hypecheck-api
sleep 2
systemctl --user status hypecheck-api --no-pager"

echo "✅ HypeCheck API deployed on port 3347"
echo "Next: Add proxy route in wisechef landing server.js"
