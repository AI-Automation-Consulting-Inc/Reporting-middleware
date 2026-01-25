# Auto-Deploy to Lightsail Setup

## 1. Get Your Lightsail SSH Key

On your local machine:
```powershell
# If you have the .pem key file
cat C:\path\to\your-lightsail-key.pem | clip
```

Or from Lightsail console: Account → SSH Keys → Download

## 2. Add GitHub Secrets

Go to: https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware/settings/secrets/actions

Add these secrets:

| Secret Name | Value |
|------------|-------|
| `LIGHTSAIL_HOST` | Your Lightsail public IP (e.g., `18.xxx.xxx.xxx`) |
| `LIGHTSAIL_USER` | Usually `ubuntu` or `bitnami` |
| `LIGHTSAIL_SSH_KEY` | Paste your private SSH key (entire .pem file content) |

## 3. Update Deployment Path

Edit `.github/workflows/deploy.yml` line 17:
```yaml
cd /path/to/Report-Middleware
```
Change to your actual path (e.g., `/home/ubuntu/Report-Middleware`)

## 4. Choose Restart Method

The workflow tries multiple restart methods. Pick ONE that matches your setup:

**Option A: systemd service** (recommended)
```bash
# On Lightsail, create: /etc/systemd/system/reporting-middleware.service
[Unit]
Description=Reporting Middleware API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Report-Middleware
Environment="PATH=/home/ubuntu/Report-Middleware/.venv/bin"
ExecStart=/home/ubuntu/Report-Middleware/.venv/bin/python -m uvicorn webapp.server:app --host 0.0.0.0 --port 8003
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable reporting-middleware
sudo systemctl start reporting-middleware
```

**Option B: supervisor** 
Install supervisor, create config in `/etc/supervisor/conf.d/reporting-middleware.conf`

**Option C: simple background process**
Uses `pkill` + `nohup` (already in the workflow)

## 5. Test

Push any change to `main`:
```powershell
git add .github/workflows/deploy.yml
git commit -m "Add auto-deploy workflow"
git push origin main
```

Check: https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware/actions

## Troubleshooting

- **SSH fails:** Verify SSH key format (should include `-----BEGIN RSA PRIVATE KEY-----`)
- **Path not found:** Update the `cd` path in deploy.yml
- **Permission denied:** Add `sudo` before systemctl or use password-less sudo
