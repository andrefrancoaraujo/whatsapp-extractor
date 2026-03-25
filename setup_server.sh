#!/bin/bash
# Setup WhatsApp Extractor server on VPS (148.230.77.21)
# Run as root

set -e

APP_DIR="/opt/whatsapp-extractor"
DIST_DIR="$APP_DIR/dist"

echo "=== Setting up WhatsApp Extractor Server ==="

# 1. Create directories
mkdir -p "$APP_DIR"/{uploads,parsed,dist}
mkdir -p "$APP_DIR/server/templates"

# 2. Copy server files (run from project directory)
cp server/app.py "$APP_DIR/server/"
cp server/templates/download.html "$APP_DIR/server/templates/"
cp requirements-server.txt "$APP_DIR/"

# 3. Create virtualenv
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-server.txt

# 4. Create systemd service
cat > /etc/systemd/system/whatsapp-extractor.service << 'EOF'
[Unit]
Description=WhatsApp Extractor Server
After=network.target

[Service]
User=root
WorkingDirectory=/opt/whatsapp-extractor/server
ExecStart=/opt/whatsapp-extractor/venv/bin/gunicorn --bind 127.0.0.1:5001 --workers 2 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Nginx config
cat > /etc/nginx/sites-available/whatsapp-extractor << 'EOF'
server {
    listen 80;
    server_name extractor.andrefrancoaraujo.shop;

    client_max_body_size 500M;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/whatsapp-extractor /etc/nginx/sites-enabled/

# 6. Start services
systemctl daemon-reload
systemctl enable whatsapp-extractor
systemctl start whatsapp-extractor
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup complete! ==="
echo "Server running at: http://extractor.andrefrancoaraujo.shop"
echo ""
echo "Next steps:"
echo "1. Add DNS A record: extractor.andrefrancoaraujo.shop -> 148.230.77.21"
echo "2. Run: certbot --nginx -d extractor.andrefrancoaraujo.shop"
echo "3. Upload the .exe to: $DIST_DIR/WhatsAppExtractor.exe"
echo ""
