#!/bin/bash
# AWS Lightsail Deployment Script
# This script sets up the application on AWS Lightsail with SSL support

set -e

echo "🚀 Deploying Report-Middleware to AWS Lightsail..."

# Configuration
APP_DIR="/opt/report-middleware"
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="report-middleware"
DOMAIN="${DOMAIN:-localhost}"  # Set via environment or default to localhost

# 1. Update system packages
echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. Install dependencies
echo "📦 Installing Python and dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv nginx supervisor

# 3. Create application directory
echo "📁 Setting up application directory..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR
cd $APP_DIR

# 4. Clone/copy application code (assumes code is already on server)
# If deploying from git:
# git clone <your-repo-url> .
# Or if using rsync/scp, files should already be present

# 5. Create virtual environment and install dependencies
echo "🐍 Setting up Python virtual environment..."
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Create database
echo "💾 Setting up database..."
python3 create_enhanced_dummy_db.py

# 7. Set up environment variables
echo "🔧 Configuring environment..."
cat > $APP_DIR/.env << EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
DUMMY_DB_NAME=enhanced_sales.db
ENVIRONMENT=production
DOMAIN=${DOMAIN}
EOF

# 8. Configure Nginx with SSL (using existing certificate)
echo "🌐 Configuring Nginx with SSL..."
sudo tee /etc/nginx/sites-available/$SERVICE_NAME > /dev/null <<'NGINX_EOF'
upstream app_server {
    server 127.0.0.1:8003 fail_timeout=0;
}

server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;
    
    # SSL Certificate paths (update these to your existing certificate paths)
    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Serve static files
    location /web/ {
        alias /opt/report-middleware/web/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Proxy API requests to FastAPI
    location /api/ {
        proxy_pass http://app_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_buffering off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Root redirects to web interface
    location = / {
        return 301 /web/index.html;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
    
    # Logging
    access_log /var/log/nginx/report-middleware-access.log;
    error_log /var/log/nginx/report-middleware-error.log;
}
NGINX_EOF

# Replace domain placeholder
sudo sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/$SERVICE_NAME

# Enable site
sudo ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and reload Nginx
echo "🧪 Testing Nginx configuration..."
sudo nginx -t
sudo systemctl reload nginx

# 9. Configure Supervisor to manage the application
echo "⚙️  Configuring Supervisor..."
sudo tee /etc/supervisor/conf.d/$SERVICE_NAME.conf > /dev/null <<SUPERVISOR_EOF
[program:$SERVICE_NAME]
command=$VENV_DIR/bin/uvicorn webapp.server:app --host 127.0.0.1 --port 8003 --workers 2
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/$SERVICE_NAME.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="$VENV_DIR/bin",OPENAI_API_KEY="$OPENAI_API_KEY"
SUPERVISOR_EOF

# Reload supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart $SERVICE_NAME

# 10. Enable services to start on boot
echo "🔄 Enabling services..."
sudo systemctl enable nginx
sudo systemctl enable supervisor

echo "✅ Deployment complete!"
echo ""
echo "📋 Service Status:"
sudo supervisorctl status $SERVICE_NAME
echo ""
echo "🌐 Your application should be available at:"
echo "   https://$DOMAIN"
echo ""
echo "📊 Useful commands:"
echo "   - Check app logs: sudo tail -f /var/log/supervisor/$SERVICE_NAME.log"
echo "   - Check nginx logs: sudo tail -f /var/log/nginx/report-middleware-error.log"
echo "   - Restart app: sudo supervisorctl restart $SERVICE_NAME"
echo "   - Restart nginx: sudo systemctl restart nginx"
