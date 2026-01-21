# AWS Lightsail Deployment Guide

## Prerequisites
- AWS Lightsail account
- Docker installed on Lightsail instance
- Your OpenAI API key

## Step 1: Create Lightsail Instance

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

## Step 3: Install Docker on Lightsail

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

## Step 4: Clone Your Repository

```bash
# Install git if needed
sudo apt-get install git -y

# Clone your repository
git clone https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware.git
cd Reporting-middleware

# Checkout WebUI branch
git checkout WebUI
```

## Step 5: Configure Environment

```bash
# Create .env file from example
cp .env.example .env

# Edit .env file with your API key
nano .env
# Add your actual OPENAI_API_KEY
# Save: Ctrl+X, then Y, then Enter
```

## Step 6: Generate Database

```bash
# Generate the sales database
python3 create_enhanced_dummy_db.py
```

## Step 7: Build and Run Docker Container

```bash
# Build the Docker image
docker build -t report-middleware:latest .

# Run using docker-compose (recommended)
docker compose up -d

# Or run directly with docker
docker run -d \
  --name report-middleware \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config_store:/app/config_store \
  --restart unless-stopped \
  report-middleware:latest
```

## Step 8: Configure Lightsail Firewall

1. Go to Lightsail console
2. Click on your instance
3. Go to "Networking" tab
4. Under "IPv4 Firewall", click "Add rule"
5. Add:
   - **Application**: Custom
   - **Protocol**: TCP
   - **Port**: 8000
6. Click "Create"

## Step 9: Access Your Application

Your app will be available at:
```
http://your-lightsail-ip:8000
```

Find your IP in Lightsail console under your instance details.

## Step 10: Set Up HTTPS (Optional but Recommended)

### Option A: Use Lightsail Load Balancer
1. Create Lightsail Load Balancer
2. Attach SSL certificate
3. Point to your instance on port 8000

### Option B: Use Caddy Reverse Proxy

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy -y

# Create Caddyfile
sudo nano /etc/caddy/Caddyfile
```

Add:
```
your-domain.com {
    reverse_proxy localhost:8000
}
```

```bash
# Restart Caddy
sudo systemctl restart caddy
```

## Useful Commands

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

### Container won't start
```bash
# Check logs
docker logs report-middleware

# Verify environment variables
docker exec report-middleware env | grep OPENAI
```

### Port already in use
```bash
# Find process using port 8000
sudo lsof -i :8000
sudo kill -9 <PID>
```

### Out of memory
- Upgrade Lightsail instance plan
- Or reduce FACT_ROW_COUNT in .env

### API key issues
```bash
# Verify .env file
cat .env
# Update and restart
docker compose restart
```

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

1. Set up monitoring (CloudWatch, Datadog, etc.)
2. Configure database backups
3. Set up CI/CD pipeline
4. Add authentication to the web app
5. Configure custom domain
