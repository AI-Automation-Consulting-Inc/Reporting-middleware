# PowerShell script to create and deploy package to AWS Lightsail
# Usage: .\deploy-to-lightsail.ps1 -LightsailIP "YOUR_IP" -KeyPath "path\to\key.pem" -Domain "your-domain.com"

param(
    [Parameter(Mandatory=$true)]
    [string]$LightsailIP,
    
    [Parameter(Mandatory=$true)]
    [string]$KeyPath,
    
    [Parameter(Mandatory=$true)]
    [string]$Domain,
    
    [string]$User = "ubuntu",
    
    [Parameter(Mandatory=$true)]
    [string]$OpenAIKey
)

Write-Host "🚀 Deploying Report-Middleware to AWS Lightsail..." -ForegroundColor Cyan
Write-Host ""

# 1. Create deployment package
Write-Host "📦 Creating deployment package..." -ForegroundColor Yellow
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packageName = "report-middleware-$timestamp.tar.gz"

# Use WSL or Git Bash to create tar.gz if available
try {
    # Try using wsl
    wsl tar -czf $packageName `
        --exclude='.git' `
        --exclude='.venv' `
        --exclude='__pycache__' `
        --exclude='*.pyc' `
        --exclude='*.db' `
        --exclude='*.log' `
        --exclude='last_query_*' `
        --exclude='results*.jsonl' `
        .
    Write-Host "✅ Package created: $packageName" -ForegroundColor Green
} catch {
    Write-Host "⚠️  WSL not available, trying Git Bash..." -ForegroundColor Yellow
    try {
        & "C:\Program Files\Git\usr\bin\tar.exe" -czf $packageName `
            --exclude='.git' `
            --exclude='.venv' `
            --exclude='__pycache__' `
            --exclude='*.pyc' `
            --exclude='*.db' `
            --exclude='*.log' `
            --exclude='last_query_*' `
            --exclude='results*.jsonl' `
            .
        Write-Host "✅ Package created: $packageName" -ForegroundColor Green
    } catch {
        Write-Host "❌ Error: Could not create tar.gz package" -ForegroundColor Red
        Write-Host "   Please install WSL or Git Bash, or create package manually" -ForegroundColor Red
        exit 1
    }
}

# 2. Transfer package to Lightsail
Write-Host ""
Write-Host "📤 Transferring package to Lightsail ($LightsailIP)..." -ForegroundColor Yellow

$scpCommand = "scp -i `"$KeyPath`" $packageName ${User}@${LightsailIP}:~/"
Write-Host "   Running: $scpCommand" -ForegroundColor Gray

try {
    # Use SSH from Windows or WSL
    if (Get-Command ssh -ErrorAction SilentlyContinue) {
        & scp -i "$KeyPath" $packageName "${User}@${LightsailIP}:~/"
        Write-Host "✅ Package transferred successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ Error: SSH not found. Please install OpenSSH or use WSL" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ Error transferring package: $_" -ForegroundColor Red
    exit 1
}

# 3. Run deployment on remote server
Write-Host ""
Write-Host "🔧 Running deployment on remote server..." -ForegroundColor Yellow

$deployCommands = @"
set -e
echo '📂 Preparing application directory...'
sudo mkdir -p /opt/report-middleware
sudo chown \$USER:\$USER /opt/report-middleware
tar -xzf ~/$packageName -C /opt/report-middleware
cd /opt/report-middleware

echo '🔑 Setting environment variables...'
export OPENAI_API_KEY='$OpenAIKey'
export DOMAIN='$Domain'

echo '🚀 Running deployment script...'
chmod +x lightsail-deploy.sh
sudo -E ./lightsail-deploy.sh

echo ''
echo '✅ Deployment complete!'
echo ''
echo '🌐 Your application is available at: https://$Domain'
echo ''
"@

try {
    $deployCommands | & ssh -i "$KeyPath" "${User}@${LightsailIP}" "bash -s"
    Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
} catch {
    Write-Host "❌ Error during deployment: $_" -ForegroundColor Red
    exit 1
}

# 4. Cleanup local package
Write-Host ""
Write-Host "🧹 Cleaning up local package..." -ForegroundColor Yellow
Remove-Item $packageName -Force
Write-Host "✅ Cleanup complete" -ForegroundColor Green

# 5. Summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "           DEPLOYMENT SUMMARY" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Application deployed to: $LightsailIP" -ForegroundColor Green
Write-Host "🌐 Access URL: https://$Domain" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Useful Commands:" -ForegroundColor Yellow
Write-Host "   SSH to server:" -ForegroundColor Gray
Write-Host "     ssh -i `"$KeyPath`" ${User}@${LightsailIP}" -ForegroundColor White
Write-Host ""
Write-Host "   Check application status:" -ForegroundColor Gray
Write-Host "     ssh -i `"$KeyPath`" ${User}@${LightsailIP} 'sudo supervisorctl status'" -ForegroundColor White
Write-Host ""
Write-Host "   View logs:" -ForegroundColor Gray
Write-Host "     ssh -i `"$KeyPath`" ${User}@${LightsailIP} 'sudo tail -f /var/log/supervisor/report-middleware.log'" -ForegroundColor White
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
