# Google Analytics 4 Setup Guide

Your site now has GA4 tracking code installed! Follow these steps to activate it.

## Step 1: Get Your GA4 Measurement ID

1. Go to [Google Analytics](https://analytics.google.com)
2. Click **Admin** (gear icon in bottom left)
3. Click **Create Property** (or select existing one)
4. Fill in:
   - **Property name**: `Report Middleware - AI Automation Consulting`
   - **Reporting time zone**: Your timezone
   - **Currency**: USD (or your preference)
5. Click **Next** and complete setup
6. You'll get a **Measurement ID** like `G-XXXXXXXXXX`
7. **Copy this ID**

## Step 2: Add Your Measurement ID to Code

Open [web/index.html](web/index.html) and replace **both occurrences** of `G-XXXXXXXXXX` with your actual ID:

**Line 9:**
```html
<script async src="https://www.googletagmanager.com/gtag/js?id=G-YOUR_ACTUAL_ID"></script>
```

**Line 13:**
```javascript
gtag('config', 'G-YOUR_ACTUAL_ID');
```

Save the file.

## Step 3: Commit and Push

```powershell
git add web/index.html
git commit -m "Add GA4 tracking with measurement ID"
git push origin main
```

## Step 4: Deploy to Lightsail

```bash
# SSH into your Lightsail instance
ssh -i /path/to/key.pem ubuntu@your-lightsail-ip

# Navigate to repo
cd ~/report-middleware

# Pull latest changes
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

## Step 5: Verify Tracking Works

### Method 1: Real-time Report
1. Go to Google Analytics
2. Click **Reports** → **Realtime**
3. Open your site: `https://reports-ai.utils.product-led-growth.com`
4. Within 30 seconds, you should see yourself as an active user

### Method 2: Browser Console
1. Open your site
2. Press F12 (DevTools)
3. Go to **Console** tab
4. Type: `gtag`
5. If you see a function, GA4 is installed ✅

### Method 3: Network Tab
1. Open your site with DevTools (F12)
2. Go to **Network** tab
3. Reload page
4. Filter by "gtag" or "google-analytics"
5. You should see requests to `www.google-analytics.com`

## What GA4 Will Track

Once live, you'll see:

### Real-time Data (updates every 30 sec)
- Active users right now
- Pages being viewed
- Traffic sources
- Geographic location

### Historical Data (24-48 hours delay)
- **Acquisition**: How users find your site
  - Direct traffic
  - Referrals (LinkedIn, Twitter, etc.)
  - Google search
  
- **Engagement**: What users do
  - Page views
  - Session duration
  - Bounce rate
  - Pages per session
  
- **Demographics**: Who your users are
  - Country, city, language
  - Device type (mobile, desktop, tablet)
  - Browser, OS
  
- **User Flow**: How users navigate
  - Landing pages
  - Exit pages
  - Navigation paths

## Track Custom Events (Optional)

To track specific actions (like query submissions), add to your HTML:

```javascript
// Track when user submits a query
function trackQuery(question) {
  gtag('event', 'query_submitted', {
    'event_category': 'User Interaction',
    'event_label': question,
    'value': 1
  });
}

// Track when chart is generated
function trackChart(chartType) {
  gtag('event', 'chart_generated', {
    'event_category': 'Feature Usage',
    'event_label': chartType,
    'value': 1
  });
}
```

Then call these functions in your code:
```javascript
// After user submits query
trackQuery(userQuestion);

// After chart is rendered
trackChart('bar'); // or 'line', 'kpi', etc.
```

## Troubleshooting

### Not Seeing Data in GA4

**Check 1**: Verify measurement ID is correct
```javascript
// In browser console
gtag('get', 'G-YOUR_ID', 'measurement_id', (value) => console.log(value));
```

**Check 2**: Check ad blockers
- Disable ad blockers or use incognito mode
- Some extensions block GA4

**Check 3**: Check Network tab
- Open DevTools → Network
- Look for requests to `google-analytics.com`
- If no requests, GA4 code may not be loading

**Check 4**: Wait 24-48 hours
- Real-time shows instantly
- Historical reports take 1-2 days

### Privacy & GDPR Compliance

If you have EU visitors, add a cookie consent banner:

```html
<!-- Simple cookie notice -->
<div id="cookie-notice" style="position:fixed;bottom:0;left:0;right:0;background:#333;color:#fff;padding:1rem;text-align:center;display:none;">
  This site uses cookies to track usage. 
  <button onclick="acceptCookies()">Accept</button>
</div>

<script>
function acceptCookies() {
  localStorage.setItem('cookiesAccepted', 'true');
  document.getElementById('cookie-notice').style.display = 'none';
  // Load GA4 here if you moved it to conditional loading
}

// Show notice if not accepted
if (!localStorage.getItem('cookiesAccepted')) {
  document.getElementById('cookie-notice').style.display = 'block';
}
</script>
```

## Next Steps

1. Replace `G-XXXXXXXXXX` with your actual ID
2. Commit and deploy
3. Check Real-time report in GA4
4. Share the link on LinkedIn/Twitter
5. Watch traffic come in!

## Resources

- [GA4 Documentation](https://support.google.com/analytics/answer/9304153)
- [GA4 Events Reference](https://developers.google.com/analytics/devguides/collection/ga4/events)
- [Google Tag Manager](https://tagmanager.google.com/) (advanced tracking)
