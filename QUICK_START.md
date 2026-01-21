# Quick Start Guide

Fast-track deployment for Report-Middleware on AWS Lightsail with Docker and SSL.

## Checklist Before Deployment

- [ ] AWS Lightsail account
- [ ] SSH key to Lightsail instance
- [ ] Domain name with DNS provider
- [ ] OpenAI API key
- [ ] Let's Encrypt SSL certificate (or will create new one)

## Step-by-Step Deployment (5 minutes)

### 1. SSH into Lightsail

```bash
ssh -i /path/to/key.pem ubuntu@your-lightsail-ip
```

### 2. Install Dependencies

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
sudo apt-get install nginx git -y
exit  # Log out and back in
ssh -i /path/to/key.pem ubuntu@your-lightsail-ip
```

### 3. Clone Repository and Setup

```bash
cd /home/ubuntu
git clone https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware.git report-middleware
cd report-middleware
git checkout main
```

### 4. Configure Environment

```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-key-here
EOF
```

### 5. Generate Database

```bash
python3 create_enhanced_dummy_db.py
```

### 6. Build and Run Container

**CRITICAL: Ensure requirements.txt has openai package before building!**

```bash
# Verify openai is in requirements.txt
grep openai requirements.txt

# Build image (this takes 1-2 minutes)
docker build -t report-middleware:latest .

# Run container
docker run -d \
  --name report-middleware \
  --restart unless-stopped \
  -p 8003:8000 \
  --env-file .env \
  -v $(pwd)/enhanced_sales.db:/app/enhanced_sales.db \
  -v $(pwd)/config_store:/app/config_store \
  report-middleware:latest

# Verify running
docker ps
docker logs report-middleware
```

### 7. Configure Nginx (If Using Domain + SSL)

```bash
# Check if certificate exists (from previous deployments)
sudo ls /etc/letsencrypt/live/

# If certificate already exists for your domain:
sudo nano /etc/nginx/sites-available/your-domain.conf
```

Add this config (replace `your-domain.com`):

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

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
sudo ln -s /etc/nginx/sites-available/your-domain.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Configure Lightsail Firewall

In AWS Lightsail console:
1. Click your instance
2. Go to "Networking" tab
3. Add IPv4 Firewall rules:
   - **HTTP**: Port 80
   - **HTTPS**: Port 443

### 9. Verify Deployment

```bash
# Check container health
docker logs report-middleware

# Test API endpoint
curl -X POST http://localhost:8003/api/query -H "Content-Type: application/json" -d '{"question":"revenue by region for last 12 months"}'

# Or open in browser
# https://your-domain.com (if using nginx + SSL)
# http://your-lightsail-ip:8003 (direct access)
```

---

## Critical Gotchas

### ⚠️ openai Package Missing

**Problem**: Docker container builds but queries fail with "openai package not installed"

**Solution**: Verify `requirements.txt` has `openai>=1.0.0` BEFORE building image:
```bash
grep openai requirements.txt
```

If missing, add it and rebuild:
```bash
echo "openai>=1.0.0" >> requirements.txt
git add requirements.txt
git commit -m "Add openai package"
git pull origin main  # Get latest
docker build -t report-middleware:latest .
```

### ⚠️ Git Merge Conflicts

**Problem**: `git pull origin main` fails with "Your local changes would be overwritten"

**Solution**: Stash changes and pull:
```bash
git stash
git pull origin main
```

### ⚠️ Port Already in Use

**Problem**: Container won't start, port 8003 already bound

**Solution**: Stop existing container:
```bash
docker stop report-middleware
docker rm report-middleware
# Then re-run docker run command
```

### ⚠️ SSL Certificate Not Found

**Problem**: Nginx config says certificate missing

**Solution**: Either create new cert with certbot, or expand existing:
```bash
# Expand existing certificate to new domain
sudo certbot --nginx -d your-new-domain.com

# Or create new certificate
sudo certbot certonly --nginx -d your-domain.com
```

### ⚠️ .env File Not Loaded

**Problem**: Container runs but queries fail with "Invalid API key"

**Solution**: Verify .env exists and passed to container:
```bash
# Check .env in container
docker exec report-middleware cat /app/.env

# If missing, rebuild with --env-file
docker stop report-middleware && docker rm report-middleware
docker run -d ... --env-file .env ...
```

---

## Upgrade Workflow

When pulling latest code with changes:

```bash
cd /home/ubuntu/report-middleware

# Get latest changes
git pull origin main

# Rebuild image (if requirements.txt changed)
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
curl http://localhost:8003
```

---

## Local Development (Windows)

See [DEVELOPMENT.md](DEVELOPMENT.md) for local setup.

Quick version:
```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your OpenAI key
python create_enhanced_dummy_db.py
python run_intent.py --question "revenue by region"
```

---

## Architecture

```
User Browser
    ↓
HTTPS (port 443)
    ↓
Nginx Reverse Proxy
    ↓
Docker Container (port 8000 → 8003)
    ↓
FastAPI Server
    ↓
OpenAI GPT-4o-mini (Intent Parser)
    ↓
SQLite Database (enhanced_sales.db)
    ↓
Chart Builder (Plotly)
    ↓
Response: JSON + Chart HTML
```

---

## Troubleshooting Quick Commands

```bash
# View container logs
docker logs report-middleware

# Check if container is running
docker ps

# Check all processes
docker ps -a

# Restart container
docker restart report-middleware

# Test HTTP endpoint
curl http://localhost:8003

# Test HTTPS endpoint
curl https://your-domain.com

# Check nginx status
sudo systemctl status nginx

# Check nginx config syntax
sudo nginx -t

# View nginx error log
sudo tail -f /var/log/nginx/error.log

# SSH into running container
docker exec -it report-middleware bash

# Check OpenAI key in container
docker exec report-middleware env | grep OPENAI
```

---

## Performance Tips

- **Instance Size**: $10/month (2GB) for testing, $20/month (4GB) for production
- **Database**: SQLite is sufficient for <100k rows. Use PostgreSQL for larger datasets.
- **Caching**: Add Redis for repeated queries
- **Monitoring**: Use CloudWatch or Datadog for alerts

---

## Next Steps

1. ✅ Application is live at `https://your-domain.com`
2. Test with sample queries in UI
3. Configure custom tenant schema in `config_store/tenant1.json`
4. Set up monitoring and backups
5. Refer to [DEPLOYMENT.md](DEPLOYMENT.md) for detailed options
