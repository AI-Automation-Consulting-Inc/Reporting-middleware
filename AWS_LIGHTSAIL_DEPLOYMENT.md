# AWS Lightsail Deployment Guide

Complete guide for deploying the Report-Middleware application to AWS Lightsail with SSL support.

## Prerequisites

- AWS Lightsail instance (Ubuntu 20.04 or newer recommended)
- Domain name pointing to your Lightsail instance
- **Existing SSL certificate** on your Lightsail instance (Let's Encrypt or other)
- SSH access to your instance
- OpenAI API key

## Quick Deployment

### 1. Prepare Your Local Files

```bash
# Ensure you're on main branch with latest changes
git status
git pull origin main

# Create deployment package
tar -czf report-middleware.tar.gz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='node_modules' \
  --exclude='enhanced_sales.db' \
  .
```

### 2. Transfer Files to Lightsail

```bash
# Replace with your Lightsail instance details
LIGHTSAIL_IP="YOUR_INSTANCE_IP"
LIGHTSAIL_USER="ubuntu"  # or 'bitnami' depending on your setup
KEY_PATH="path/to/your-lightsail-key.pem"

# Transfer the package
scp -i $KEY_PATH report-middleware.tar.gz $LIGHTSAIL_USER@$LIGHTSAIL_IP:~/

# SSH into your instance
ssh -i $KEY_PATH $LIGHTSAIL_USER@$LIGHTSAIL_IP
```

### 3. Extract and Prepare Application

```bash
# On the Lightsail instance
cd ~
mkdir -p /opt/report-middleware
sudo chown $USER:$USER /opt/report-middleware
tar -xzf report-middleware.tar.gz -C /opt/report-middleware
cd /opt/report-middleware
```

### 4. Configure Environment

```bash
# Set your environment variables
export OPENAI_API_KEY="sk-..."
export DOMAIN="your-domain.com"

# Make the deployment script executable
chmod +x lightsail-deploy.sh
```

### 5. Update SSL Certificate Paths

If your existing SSL certificates are in a different location than the default `/etc/letsencrypt/live/`, edit the deployment script before running:

```bash
nano lightsail-deploy.sh
```

Update these lines to match your certificate locations:
```nginx
ssl_certificate /path/to/your/fullchain.pem;
ssl_certificate_key /path/to/your/privkey.pem;
```

Common certificate locations:
- **Let's Encrypt**: `/etc/letsencrypt/live/YOUR_DOMAIN/`
- **Lightsail Load Balancer**: Managed automatically via AWS
- **Custom certificates**: Check your nginx config at `/etc/nginx/sites-enabled/`

### 6. Run Deployment

```bash
# Execute the deployment script
sudo -E ./lightsail-deploy.sh
```

The script will:
- ✅ Install system dependencies (Python, Nginx, Supervisor)
- ✅ Set up Python virtual environment
- ✅ Install Python packages
- ✅ Create the demo database
- ✅ Configure Nginx with your existing SSL certificate
- ✅ Set up Supervisor to manage the application
- ✅ Start the service

### 7. Verify Deployment

```bash
# Check application status
sudo supervisorctl status report-middleware

# Check logs
sudo tail -f /var/log/supervisor/report-middleware.log

# Test the application
curl -k https://localhost/health
curl -k https://localhost/api/sample-queries
```

### 8. Configure Firewall

Ensure your Lightsail firewall allows HTTPS traffic:

```bash
# Via AWS Console:
# Lightsail → Instances → Your Instance → Networking tab
# Add rule: HTTPS, TCP, 443

# Or via CLI:
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp   # For HTTP to HTTPS redirect
sudo ufw status
```

## Using Existing SSL Certificates

### Option 1: Let's Encrypt (Certbot)

If you already have Let's Encrypt certificates:

```bash
# Certificates are typically at:
/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem
/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem

# The deployment script uses these paths by default
# No changes needed!
```

To renew certificates:
```bash
sudo certbot renew --dry-run  # Test renewal
sudo certbot renew            # Actual renewal
sudo systemctl reload nginx   # Reload nginx after renewal
```

### Option 2: Lightsail Load Balancer with SSL

If using Lightsail's managed load balancer with SSL:

1. Keep the application running on HTTP (port 8003)
2. Configure load balancer to handle SSL termination
3. Update nginx config to listen only on HTTP:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Rest of your config...
}
```

### Option 3: Custom SSL Certificate

If you have custom SSL certificates:

```bash
# Copy your certificates to a secure location
sudo mkdir -p /etc/ssl/private
sudo cp fullchain.pem /etc/ssl/certs/your-domain.crt
sudo cp privkey.pem /etc/ssl/private/your-domain.key
sudo chmod 600 /etc/ssl/private/your-domain.key

# Update nginx config before running deployment
nano lightsail-deploy.sh
# Change certificate paths to:
ssl_certificate /etc/ssl/certs/your-domain.crt;
ssl_certificate_key /etc/ssl/private/your-domain.key;
```

## Post-Deployment Management

### Application Management

```bash
# Start/Stop/Restart application
sudo supervisorctl start report-middleware
sudo supervisorctl stop report-middleware
sudo supervisorctl restart report-middleware

# Check status
sudo supervisorctl status

# View logs (real-time)
sudo tail -f /var/log/supervisor/report-middleware.log

# View all logs
sudo less /var/log/supervisor/report-middleware.log
```

### Nginx Management

```bash
# Test configuration
sudo nginx -t

# Reload (no downtime)
sudo systemctl reload nginx

# Restart
sudo systemctl restart nginx

# Check status
sudo systemctl status nginx

# View access logs
sudo tail -f /var/log/nginx/report-middleware-access.log

# View error logs
sudo tail -f /var/log/nginx/report-middleware-error.log
```

### Update Application Code

```bash
# On your local machine, create new package
cd /path/to/Report-Middleware
git pull origin main
tar -czf report-middleware-update.tar.gz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='enhanced_sales.db' \
  .

# Transfer to server
scp -i $KEY_PATH report-middleware-update.tar.gz $LIGHTSAIL_USER@$LIGHTSAIL_IP:~/

# On the server
ssh -i $KEY_PATH $LIGHTSAIL_USER@$LIGHTSAIL_IP
cd /opt/report-middleware
sudo supervisorctl stop report-middleware
tar -xzf ~/report-middleware-update.tar.gz -C /opt/report-middleware
source .venv/bin/activate
pip install -r requirements.txt --upgrade
sudo supervisorctl start report-middleware
```

### Database Updates

```bash
# Backup existing database
cp enhanced_sales.db enhanced_sales.db.backup

# Regenerate with new data
source .venv/bin/activate
python3 create_enhanced_dummy_db.py

# Restart application
sudo supervisorctl restart report-middleware
```

## Monitoring and Troubleshooting

### Check Application Health

```bash
# Health endpoint
curl https://your-domain.com/health

# API endpoints
curl https://your-domain.com/api/database-info
curl https://your-domain.com/api/sample-queries
```

### Common Issues

**Issue: Application won't start**
```bash
# Check logs for errors
sudo tail -100 /var/log/supervisor/report-middleware.log

# Check if port 8003 is available
sudo netstat -tlnp | grep 8003

# Verify Python dependencies
cd /opt/report-middleware
source .venv/bin/activate
pip list
```

**Issue: Nginx returns 502 Bad Gateway**
```bash
# Check if application is running
sudo supervisorctl status report-middleware

# Check nginx error logs
sudo tail -f /var/log/nginx/report-middleware-error.log

# Verify upstream connection
curl http://127.0.0.1:8003/api/database-info
```

**Issue: SSL certificate errors**
```bash
# Verify certificate paths
sudo ls -la /etc/letsencrypt/live/YOUR_DOMAIN/

# Check certificate expiry
sudo openssl x509 -in /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem -text -noout | grep "Not After"

# Test SSL configuration
sudo nginx -t
```

**Issue: OpenAI API errors**
```bash
# Verify API key is set
sudo supervisorctl stop report-middleware
nano /etc/supervisor/conf.d/report-middleware.conf
# Update environment=... line with correct OPENAI_API_KEY
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start report-middleware
```

## Security Best Practices

1. **Keep SSL certificates updated**
   ```bash
   # Set up auto-renewal for Let's Encrypt
   sudo crontab -e
   # Add: 0 0 * * * certbot renew --quiet && systemctl reload nginx
   ```

2. **Restrict API key access**
   ```bash
   # Ensure .env file has restricted permissions
   chmod 600 /opt/report-middleware/.env
   ```

3. **Enable UFW firewall**
   ```bash
   sudo ufw enable
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # HTTP
   sudo ufw allow 443/tcp  # HTTPS
   ```

4. **Regular updates**
   ```bash
   # System packages
   sudo apt-get update && sudo apt-get upgrade -y
   
   # Python packages
   cd /opt/report-middleware
   source .venv/bin/activate
   pip list --outdated
   pip install -r requirements.txt --upgrade
   ```

## Performance Tuning

### Increase Uvicorn Workers

Edit supervisor config:
```bash
sudo nano /etc/supervisor/conf.d/report-middleware.conf
```

Change workers based on your instance size:
```ini
# For 1GB RAM: --workers 2
# For 2GB RAM: --workers 4
# For 4GB+ RAM: --workers 8
command=/opt/report-middleware/.venv/bin/uvicorn webapp.server:app --host 127.0.0.1 --port 8003 --workers 4
```

Restart:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart report-middleware
```

### Nginx Caching

Add to nginx config for better performance:
```nginx
# Inside server block
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

## Cost Optimization

- **Lightsail Instance**: Start with $5/month (1GB RAM) instance
- **Snapshots**: Create weekly snapshots for backups ($0.05/GB/month)
- **Static IPs**: Free when attached to running instance
- **Bandwidth**: 1TB-3TB included (depending on plan)

## Support and Monitoring

Set up CloudWatch or simple monitoring:

```bash
# Create monitoring script
cat > /opt/report-middleware/monitor.sh << 'EOF'
#!/bin/bash
if ! curl -sf http://127.0.0.1:8003/api/database-info > /dev/null; then
    echo "Application is down, restarting..."
    supervisorctl restart report-middleware
fi
EOF

chmod +x /opt/report-middleware/monitor.sh

# Add to crontab
crontab -e
# Add: */5 * * * * /opt/report-middleware/monitor.sh
```

## Next Steps

After successful deployment:

1. ✅ Access your application at `https://your-domain.com`
2. ✅ Test sample queries in the UI
3. ✅ Monitor logs for any issues
4. ✅ Set up regular backups
5. ✅ Configure monitoring/alerting
6. ✅ Update DNS if needed
7. ✅ Share with your team!

---

**Need help?** Check the logs first, then review the troubleshooting section above.
