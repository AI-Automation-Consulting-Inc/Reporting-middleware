# Pre-Launch Checklist for AWS Lightsail

Complete this checklist before deploying to production.

## ✅ Pre-Deployment Checklist

### AWS Lightsail Setup
- [ ] Lightsail instance created (Ubuntu 20.04+)
- [ ] Static IP attached to instance
- [ ] Domain DNS A record pointing to static IP
- [ ] SSH key pair downloaded and accessible
- [ ] Firewall configured (ports 22, 80, 443 open)

### SSL Certificate
- [ ] Existing SSL certificate confirmed on server
- [ ] Certificate location identified (e.g., `/etc/letsencrypt/live/DOMAIN/`)
- [ ] Certificate expiry date checked (should be valid >30 days)
- [ ] Auto-renewal configured (if using Let's Encrypt)

### Application Configuration
- [ ] OpenAI API key obtained (`sk-...`)
- [ ] API key tested and working
- [ ] Domain name confirmed
- [ ] Environment variables documented

### Local Preparation
- [ ] Code merged to main branch ✓
- [ ] All tests passing
- [ ] Dependencies listed in requirements.txt
- [ ] Database creation script tested
- [ ] Web UI tested locally

## 🚀 Deployment Steps

### 1. Environment Setup

```bash
# Set your variables
$LIGHTSAIL_IP = "YOUR_INSTANCE_IP"
$KEY_PATH = "path\to\your-lightsail-key.pem"
$DOMAIN = "your-domain.com"
$OPENAI_KEY = "sk-..."
```

### 2. Verify SSL Certificate on Server

SSH into your Lightsail instance first:

```bash
ssh -i $KEY_PATH ubuntu@$LIGHTSAIL_IP
```

Check existing certificates:

```bash
# For Let's Encrypt
sudo ls -la /etc/letsencrypt/live/
sudo certbot certificates

# For custom certificates
sudo ls -la /etc/ssl/certs/
sudo ls -la /etc/nginx/ssl/  # or wherever you stored them
```

**Note the exact paths** - you may need to update `lightsail-deploy.sh` if they differ from:
- `/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem`
- `/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem`

Exit the SSH session:
```bash
exit
```

### 3. Update Certificate Paths (if needed)

If your certificates are in a different location, edit the deployment script:

```powershell
# Open the script
code lightsail-deploy.sh

# Update these lines (around line 80):
ssl_certificate /your/actual/path/fullchain.pem;
ssl_certificate_key /your/actual/path/privkey.pem;
```

### 4. Deploy Using PowerShell Script

```powershell
.\deploy-to-lightsail.ps1 `
  -LightsailIP $LIGHTSAIL_IP `
  -KeyPath $KEY_PATH `
  -Domain $DOMAIN `
  -OpenAIKey $OPENAI_KEY
```

**OR** Deploy manually:

```bash
# 1. Create package
tar -czf report-middleware.tar.gz --exclude='.git' --exclude='.venv' --exclude='__pycache__' --exclude='*.db' .

# 2. Transfer
scp -i $KEY_PATH report-middleware.tar.gz ubuntu@$LIGHTSAIL_IP:~/

# 3. Deploy
ssh -i $KEY_PATH ubuntu@$LIGHTSAIL_IP
mkdir -p /opt/report-middleware
sudo chown $USER:$USER /opt/report-middleware
tar -xzf ~/report-middleware.tar.gz -C /opt/report-middleware
cd /opt/report-middleware
export OPENAI_API_KEY="$OPENAI_KEY"
export DOMAIN="$DOMAIN"
chmod +x lightsail-deploy.sh
sudo -E ./lightsail-deploy.sh
```

### 5. Monitor Deployment

Watch the deployment output for any errors. The script will:
1. ✅ Install system dependencies
2. ✅ Set up Python virtual environment
3. ✅ Install Python packages
4. ✅ Create demo database
5. ✅ Configure Nginx with SSL
6. ✅ Set up Supervisor
7. ✅ Start the application

### 6. Verify Deployment

```bash
# From your Lightsail instance:

# Check application status
sudo supervisorctl status report-middleware

# Check logs
sudo tail -f /var/log/supervisor/report-middleware.log

# Test endpoints
curl https://localhost/health
curl https://localhost/api/database-info
```

### 7. Test from Browser

Open your browser and navigate to:
- `https://your-domain.com`

Verify:
- [ ] SSL certificate is valid (green lock in browser)
- [ ] Database info card loads
- [ ] Sample queries display
- [ ] Run a test query: "revenue by region"
- [ ] Chart displays correctly
- [ ] AI insights appear
- [ ] Data table shows results

## 🔧 Post-Deployment Configuration

### Set Up Monitoring

```bash
# Create monitoring script
sudo tee /opt/report-middleware/monitor.sh > /dev/null << 'EOF'
#!/bin/bash
if ! curl -sf http://127.0.0.1:8003/api/database-info > /dev/null; then
    echo "$(date): Application is down, restarting..." >> /var/log/report-middleware-monitor.log
    supervisorctl restart report-middleware
fi
EOF

sudo chmod +x /opt/report-middleware/monitor.sh

# Add to crontab
crontab -e
# Add this line:
*/5 * * * * /opt/report-middleware/monitor.sh
```

### Configure Log Rotation

```bash
sudo tee /etc/logrotate.d/report-middleware > /dev/null << 'EOF'
/var/log/supervisor/report-middleware.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    postrotate
        supervisorctl signal HUP report-middleware
    endscript
}
EOF
```

### Set Up SSL Auto-Renewal (Let's Encrypt)

If using Let's Encrypt:

```bash
# Test renewal
sudo certbot renew --dry-run

# Add renewal to crontab
sudo crontab -e
# Add:
0 0 * * * certbot renew --quiet && systemctl reload nginx
```

### Enable CloudWatch (Optional)

For AWS CloudWatch monitoring:

```bash
# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure to send logs
# Follow: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/install-CloudWatch-Agent-on-EC2-Instance.html
```

## 📊 Performance Tuning

### Adjust Workers Based on Instance Size

```bash
sudo nano /etc/supervisor/conf.d/report-middleware.conf

# Update workers:
# 1GB RAM (512MB): --workers 1
# 1GB RAM: --workers 2
# 2GB RAM: --workers 4
# 4GB+ RAM: --workers 8

sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart report-middleware
```

### Enable Nginx Caching

```bash
sudo nano /etc/nginx/sites-available/report-middleware

# Add inside server block:
location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}

sudo nginx -t && sudo systemctl reload nginx
```

## 🛡️ Security Hardening

### Update System Packages

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get autoremove -y
```

### Configure UFW Firewall

```bash
sudo ufw enable
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw status
```

### Secure SSH

```bash
# Disable password authentication
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
# Set: PermitRootLogin no

sudo systemctl restart ssh
```

### Restrict File Permissions

```bash
chmod 600 /opt/report-middleware/.env
sudo chown root:root /etc/supervisor/conf.d/report-middleware.conf
sudo chmod 644 /etc/supervisor/conf.d/report-middleware.conf
```

## 📋 Maintenance Tasks

### Weekly
- [ ] Check application logs for errors
- [ ] Verify SSL certificate expiry date
- [ ] Review disk usage
- [ ] Test application health endpoint

### Monthly
- [ ] Update system packages
- [ ] Update Python dependencies
- [ ] Review and rotate logs
- [ ] Create instance snapshot (backup)

### Quarterly
- [ ] Review and optimize database
- [ ] Audit API usage and costs
- [ ] Review security configurations
- [ ] Test disaster recovery procedure

## 🆘 Emergency Procedures

### Application Not Responding

```bash
# Check status
sudo supervisorctl status report-middleware

# Restart application
sudo supervisorctl restart report-middleware

# If still not working, check logs
sudo tail -100 /var/log/supervisor/report-middleware.log
```

### Nginx Not Working

```bash
# Check status
sudo systemctl status nginx

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx

# Check error logs
sudo tail -100 /var/log/nginx/report-middleware-error.log
```

### SSL Certificate Expired

```bash
# Renew immediately
sudo certbot renew --force-renewal

# Reload nginx
sudo systemctl reload nginx

# Verify
sudo certbot certificates
```

### Database Corrupted

```bash
# Stop application
sudo supervisorctl stop report-middleware

# Backup current database
cp /opt/report-middleware/enhanced_sales.db /opt/report-middleware/enhanced_sales.db.backup

# Regenerate database
cd /opt/report-middleware
source .venv/bin/activate
python3 create_enhanced_dummy_db.py

# Restart application
sudo supervisorctl start report-middleware
```

## 📈 Scaling Considerations

When you outgrow a single instance:

1. **Vertical Scaling**: Upgrade to larger Lightsail instance
2. **Horizontal Scaling**: 
   - Add load balancer
   - Run multiple instances
   - Use RDS for shared database
3. **Migration to ECS/EKS**: For enterprise scale

## ✅ Launch Checklist

Before announcing to users:

- [ ] Application accessible via HTTPS
- [ ] SSL certificate valid
- [ ] All test queries working
- [ ] AI insights generating
- [ ] Charts displaying correctly
- [ ] Logs clean (no errors)
- [ ] Monitoring configured
- [ ] Backups scheduled
- [ ] Team access configured
- [ ] Documentation updated
- [ ] Support process defined

## 🎉 You're Ready to Launch!

Your Report-Middleware is now:
- ✅ Deployed on AWS Lightsail
- ✅ Secured with SSL
- ✅ Monitored and auto-restarting
- ✅ Ready for production traffic

**Access your application:**
```
https://your-domain.com
```

**Share with your team and enjoy natural language analytics!** 🚀
