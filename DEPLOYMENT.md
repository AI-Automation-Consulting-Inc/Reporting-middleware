# AWS Lightsail Deployment Guide

## Prerequisites
- AWS Lightsail account
- SSH access to Lightsail instance
- Your OpenAI API key
- Domain with DNS configured

## Deployment Options

This guide covers two deployment approaches:
1. **Docker Deployment** (Recommended) - Containerized, isolated, easier to manage
2. **Native Deployment** - Direct Python installation on Ubuntu

Choose the approach that fits your needs. Docker is recommended for production.

---

## Option 1: Docker Deployment (Recommended)

### Step 1: Create Lightsail Instance

1. Go to AWS Lightsail Console
2. Click "Create instance"
3. Select:
   - **Platform**: Linux/Unix
   - **Blueprint**: OS Only → Ubuntu 22.04 LTS
   - **Instance plan**: At least $10/month (2 GB RAM, 1 vCore)
4. Name your instance: `report-middleware`
5. Click "Create instance"

## Step 2: Connect to Your Instance

```bash
# From Lightsail console, click "Connect using SSH"
# Or use your SSH client:
ssh -i /path/to/your-key.pem ubuntu@your-lightsail-ip
```

## Step 3: Install Docker

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt-get install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version

# Log out and back in for group changes to take effect
exit
# Then SSH back in
```

## Step 4: Clone Repository and Setup

```bash
# Install git if needed
sudo apt-get install git -y

# Clone repository
cd /home/ubuntu
git clone https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware.git report-middleware
cd report-middleware
git checkout main
```

## Step 5: Configure Environment and Generate Database

```bash
# Create .env file
cat > .env << 'EOF'
OPENAI_API_KEY=your_openai_api_key_here
EOF

# Or edit manually
nano .env
# Add: OPENAI_API_KEY=sk-...
# Save: Ctrl+X, then Y, then Enter

# Generate the sales database
python3 create_enhanced_dummy_db.py
```

## Step 6: Verify Dependencies Before Building

**CRITICAL**: Before building the Docker image, ensure `requirements.txt` contains the `openai` package:

```bash
# Check if openai is present
grep openai requirements.txt

# If missing, add it
echo "openai>=1.0.0" >> requirements.txt

# Commit to git so Docker build uses it
git add requirements.txt
git commit -m "Ensure openai package in requirements"
```

## Step 7: Build and Run Docker Container

```bash
# Build the Docker image
docker build -t report-middleware:latest .

# Run container (exposes internal port 8000 to host port 8003)
docker run -d \
  --name report-middleware \
  --restart unless-stopped \
  -p 8003:8000 \
  --env-file .env \
  -v $(pwd)/enhanced_sales.db:/app/enhanced_sales.db \
  -v $(pwd)/config_store:/app/config_store \
  report-middleware:latest

# Verify container is running
docker ps
docker logs report-middleware
```

## Step 8: Configure Nginx Reverse Proxy

If using a domain with SSL (recommended for production):

```bash
# Create nginx config for your domain
sudo nano /etc/nginx/sites-available/your-domain.com.conf
```

Add this configuration (replace `your-domain.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificate paths (update if different)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and test:

```bash
# Install nginx if not already installed
sudo apt-get install nginx -y

# Enable the site
sudo ln -s /etc/nginx/sites-available/your-domain.com.conf /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Step 9: Configure Lightsail Firewall

1. Go to Lightsail console
2. Click on your instance
3. Go to "Networking" tab
4. Under "IPv4 Firewall", add rules:
   - **HTTP**: Port 80 (for SSL redirect)
   - **HTTPS**: Port 443 (for production traffic)
   - **Custom**: Port 8003 (only if accessing without nginx)

## Step 10: Access Your Application

With nginx and SSL:
```
https://your-domain.com
```

Direct access (if firewall port 8003 is open):
```
http://your-lightsail-ip:8003
```

Find your IP in Lightsail console under instance details.

---

## Option 2: Native Deployment (Alternative)

For native deployment without Docker, use the PowerShell script from your Windows machine:

```powershell
.\deploy-to-lightsail.ps1 `
  -LightsailIP "your-lightsail-ip" `
  -KeyPath "path\to\your-key.pem" `
  -Domain "your-domain.com" `
  -OpenAIKey "sk-your-key"
```

See [AWS_LIGHTSAIL_DEPLOYMENT.md](AWS_LIGHTSAIL_DEPLOYMENT.md) for detailed native deployment instructions.

---

## SSL Certificate Setup

If you don't have SSL certificates yet:

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx -y

# Obtain certificate (nginx must be configured first)
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured by default
sudo certbot renew --dry-run
```

## Useful Docker Commands

### View logs
```bash
# Docker compose logs
docker compose logs -f

# Direct docker logs
docker logs -f report-middleware
```

### Restart application
```bash
docker compose restart

# Or
docker restart report-middleware
```

### Stop application
```bash
docker compose down

# Or
docker stop report-middleware
```

### Update application
```bash
# Pull latest code
git pull origin WebUI

# Rebuild and restart
docker compose down
docker compose up -d --build
```

### Check container status
```bash
docker ps
docker compose ps
```

### Access container shell
```bash
docker exec -it report-middleware bash
```

## Monitoring

### Check application health
```bash
curl http://localhost:8000/
```

### Monitor resource usage
```bash
docker stats report-middleware
```

## Backup

### Backup database
```bash
# Copy database from container
docker cp report-middleware:/app/enhanced_sales.db ./backup/

# Or if using volume
cp ./data/enhanced_sales.db ./backup/
```

## Troubleshooting

## Troubleshooting

### Container won't start - "openai package not installed"

**Symptom**: Container runs but queries fail with "openai package not installed"

**Cause**: `openai` package missing from `requirements.txt` when Docker image was built

**Solution**:
```bash
# On Lightsail, check container logs
docker logs report-middleware

# Fix locally on Windows/Mac
# Add openai>=1.0.0 to requirements.txt
echo "openai>=1.0.0" >> requirements.txt

# Commit and push
git add requirements.txt
git commit -m "Add openai package"
git push origin main

# On Lightsail, pull changes
cd ~/report-middleware
git stash  # If you have local changes
git pull origin main

# Rebuild Docker image
docker build -t report-middleware:latest .

# Stop and remove old container
docker stop report-middleware
docker rm report-middleware

# Run new container
docker run -d \
  --name report-middleware \
  --restart unless-stopped \
  -p 8003:8000 \
  --env-file .env \
  -v $(pwd)/enhanced_sales.db:/app/enhanced_sales.db \
  -v $(pwd)/config_store:/app/config_store \
  report-middleware:latest

# Verify
docker logs report-middleware
```

### Git merge conflict on requirements.txt

**Symptom**: `git pull origin main` fails with "Your local changes would be overwritten"

**Cause**: requirements.txt modified locally and on GitHub with conflicting changes

**Solution**:
```bash
# Stash local changes
git stash

# Pull latest from GitHub
git pull origin main

# Verify requirements.txt is correct
grep openai requirements.txt

# Rebuild container
docker build -t report-middleware:latest .
docker stop report-middleware
docker rm report-middleware
# ... run docker run command again
```

### Container won't start - Port already in use

**Symptom**: `docker run` fails with "port 8003 already in use"

**Cause**: Previous container still running or other service on port 8003

**Solution**:
```bash
# List running containers
docker ps

# Stop and remove old container
docker stop report-middleware
docker rm report-middleware

# Or force remove if stuck
docker rm -f report-middleware

# Try docker run again
```

### SSL certificate not found - Nginx fails to start

**Symptom**: `sudo systemctl status nginx` shows "no such file or directory" for certificate

**Cause**: Certificate path incorrect or not yet created

**Solution**:
```bash
# List available certificates
sudo ls /etc/letsencrypt/live/

# If domain certificate doesn't exist, create it
sudo certbot --nginx -d your-domain.com

# Or if expanding existing certificate to new domains
sudo certbot --nginx -d your-domain.com -d reports-ai.utils.product-led-growth.com

# Reload nginx
sudo systemctl reload nginx
sudo nginx -t
```

### Nginx config has encoding issues

**Symptom**: `sudo nginx -t` fails with "unknown directive" or encoding errors

**Cause**: File encoded as UTF-16 instead of UTF-8 (common from Windows editors)

**Solution**:
```bash
# Install dos2unix
sudo apt-get install dos2unix -y

# Convert the config file
sudo dos2unix /etc/nginx/sites-available/your-domain.conf

# Verify and reload
sudo nginx -t
sudo systemctl reload nginx
```

### Container running but health check fails

**Symptom**: `docker ps` shows container `unhealthy` or fails health check

**Cause**: Container startup takes time or missing endpoint (not critical for functionality)

**Solution**:
```bash
# Check if container is actually running
docker ps -a

# Check logs for actual errors
docker logs report-middleware

# Test if app is responding
curl http://localhost:8003/

# Container will become healthy after successful request
```

### Out of memory errors

**Symptom**: Container restarts unexpectedly, logs show "Killed" or "Out of memory"

**Cause**: Lightsail instance RAM insufficient for workload

**Solution**:
- Upgrade Lightsail instance to larger plan ($20/month or higher)
- Or reduce `FACT_ROW_COUNT` in `.env` if applicable

```bash
# Check current memory usage
docker stats report-middleware

# Upgrade instance: Go to Lightsail console → Click instance → Actions → Change plan
```

### API key rejected - 401 Unauthorized

**Symptom**: Queries fail with "401: Invalid API key" or similar OpenAI error

**Cause**: OpenAI API key invalid, expired, or not loaded into container

**Solution**:
```bash
# Verify API key is in .env
cat .env | grep OPENAI_API_KEY

# Check if it's loaded in container
docker exec report-middleware env | grep OPENAI_API_KEY

# If not present, update .env and restart
nano .env
# Update: OPENAI_API_KEY=sk-your-valid-key

# Restart container to load new .env
docker restart report-middleware

# Verify key is now present
docker exec report-middleware env | grep OPENAI_API_KEY
```

### Can't SSH into Lightsail instance

**Symptom**: SSH connection times out or refuses connection

**Cause**: SSH key missing, permissions wrong, or security group issue

**Solution**:
```bash
# On local machine, verify key permissions
chmod 600 /path/to/your-key.pem

# Try SSH with verbose output
ssh -v -i /path/to/your-key.pem ubuntu@your-lightsail-ip

# Or use Lightsail browser SSH
# Go to Lightsail console → Click instance → Connect using SSH button
```

## Upgrading to Latest Code

When new code is pushed to main branch:

```bash
cd ~/report-middleware

# Pull latest changes
git pull origin main

# If requirements.txt changed, rebuild image
docker build -t report-middleware:latest .

# Stop and remove old container
docker stop report-middleware
docker rm report-middleware

# Run updated container
docker run -d \
  --name report-middleware \
  --restart unless-stopped \
  -p 8003:8000 \
  --env-file .env \
  -v $(pwd)/enhanced_sales.db:/app/enhanced_sales.db \
  -v $(pwd)/config_store:/app/config_store \
  report-middleware:latest

# Verify
docker logs report-middleware
curl http://localhost:8003
```

## Monitoring Container Health

```bash
# Check logs in real-time
docker logs -f report-middleware

# View container status
docker ps -a

# Check resource usage
docker stats report-middleware

# Test API endpoint
curl -X POST http://localhost:8003/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"revenue by region for last 12 months"}'

# Test via nginx/domain (if configured)
curl https://your-domain.com
```

## Common Issues Checklist

- [ ] ✅ `openai>=1.0.0` in `requirements.txt`
- [ ] ✅ Docker image rebuilt after code changes
- [ ] ✅ `.env` file exists with valid OpenAI key
- [ ] ✅ Container running: `docker ps` shows it
- [ ] ✅ Port 8003 accessible: `curl http://localhost:8003`
- [ ] ✅ Nginx config correct: `sudo nginx -t` passes
- [ ] ✅ SSL certificate valid: browser shows green padlock
- [ ] ✅ Database file generated: `ls -la enhanced_sales.db`
- [ ] ✅ Config files mounted: `docker exec report-middleware ls config_store/`

### Troubleshooting

### Container won't start - "openai package not installed"

**Symptom**: Container runs but queries fail with "openai package not installed"



## Cost Optimization

- **Basic**: $10/month instance (2GB RAM) - suitable for testing
- **Production**: $20/month instance (4GB RAM) - better performance
- Enable auto-snapshots for backups ($0.05/GB/month)

## Security Recommendations

1. **Use HTTPS** - Set up SSL certificate
2. **Restrict SSH** - Use Lightsail firewall to limit SSH access
3. **Use .env** - Never commit API keys to git
4. **Update regularly** - Keep system and Docker updated
5. **Enable backups** - Use Lightsail snapshots

## Repository Privacy

To make your GitHub repository private:
1. Go to: https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware/settings
2. Scroll to "Danger Zone"
3. Click "Change repository visibility"
4. Select "Make private"
5. Confirm

## Next Steps

1. Review [QUICK_START.md](QUICK_START.md) for rapid deployment checklist
2. Check [DEVELOPMENT.md](DEVELOPMENT.md) for local development setup
3. Consult troubleshooting section above if issues occur
4. Set up monitoring (CloudWatch, Datadog, etc.)
5. Configure database backups
6. Add authentication to web app
7. Set up CI/CD pipeline for automated deployments
4. Select "Make private"
5. Confirm

## Next Steps

1. Set up monitoring (CloudWatch, Datadog, etc.)
2. Configure database backups
3. Set up CI/CD pipeline
4. Add authentication to the web app
5. Configure custom domain
