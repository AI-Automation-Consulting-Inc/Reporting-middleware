# Date Range Picker Feature - Deployment Guide

The application now includes a date range picker for improved UX. Users can select exact dates instead of typing "last 12 months".

## What Changed

### **Frontend (web/index.html)**
- ✅ Added date picker UI with "From" and "To" date inputs
- ✅ Added "Reset" button to restore full date range
- ✅ Date picker automatically loads min/max dates from database
- ✅ Date inputs pass values to API alongside the question

### **Backend (webapp/server.py)**
- ✅ New `/api/date-limits` endpoint returns database min/max dates
- ✅ `/api/query` endpoint now accepts `date_from` and `date_to` parameters
- ✅ Custom date range bypasses date parsing logic, directly queries specified range

## How It Works

### **User Flow**
1. Page loads → auto-fetches date limits from DB
2. Date picker displays with full range pre-selected
3. User adjusts dates if desired (optional)
4. User enters question (no longer needs to mention date range)
5. User clicks "Run Query"
6. Question + selected dates sent to API

### **Example Query**
**Before**: "revenue by region for last 12 months"  
**After**: "revenue by region" (with date picker set to 12 months)

## Deploy to Lightsail

```bash
# SSH to Lightsail
ssh -i /path/to/key.pem ubuntu@15.157.145.106

# Navigate and pull latest code
cd ~/report-middleware
git pull origin main

# Rebuild Docker image (includes new backend endpoints)
docker build -t report-middleware:latest .

# Stop old container
docker stop report-middleware
docker rm report-middleware

# Run new container with single-line command
docker run -d --name report-middleware --restart unless-stopped -p 8003:8000 --env-file .env -v $(pwd)/enhanced_sales.db:/app/enhanced_sales.db -v $(pwd)/config_store:/app/config_store report-middleware:latest

# Verify
docker logs report-middleware
```

## Test Locally First (Optional)

```powershell
# In Windows PowerShell, at repo root
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8003

# Open browser: http://localhost:8003
# You should see the date picker above the query input
```

## UI Layout

```
┌─────────────────────────────────────────────────────┐
│  Query Input                                        │
│  ┌─────────────────────────────────────────────────┐│
│  │ Ask anything... e.g., revenue by region        ││
│  └─────────────────────────────────────────────────┘│
│                                                     │
│  Date Range Picker                                  │
│  ┌──────────────────────────────────────────────┐  │
│  │ From: [2024-01-15] To: [2025-01-15] [Reset] │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  [  Run Query  ]                                    │
└─────────────────────────────────────────────────────┘
```

## API Changes

### **New Endpoint: /api/date-limits**

**Request:**
```
GET /api/date-limits
```

**Response:**
```json
{
  "min_date": "2024-01-15",
  "max_date": "2025-01-25"
}
```

### **Updated Endpoint: /api/query**

**Request (new format):**
```json
{
  "question": "revenue by region",
  "date_from": "2024-06-01",
  "date_to": "2025-01-25",
  "clarification": "yes"  // optional
}
```

**Backward compatible**: If `date_from`/`date_to` not provided, falls back to parsing date_range from question.

## Testing Checklist

- [ ] Date picker loads with database min/max dates
- [ ] Reset button restores full date range
- [ ] Date range propagates to query (check network tab in DevTools)
- [ ] Query results reflect selected date range
- [ ] Page works on mobile (responsive design)
- [ ] GA4 tracks date selection events (optional enhancement)

## Optional: Track Date Selection Events

To track when users change dates (GA4 custom events), add this to `web/index.html`:

```javascript
dateFromEl.addEventListener('change', () => {
  gtag('event', 'date_range_changed', {
    'event_category': 'User Interaction',
    'event_label': 'date_from_modified',
    'date_from': dateFromEl.value
  });
});

dateToEl.addEventListener('change', () => {
  gtag('event', 'date_range_changed', {
    'event_category': 'User Interaction',
    'event_label': 'date_to_modified',
    'date_to': dateToEl.value
  });
});
```

## Troubleshooting

### Date picker doesn't load dates
```bash
# Check if database has data
docker exec report-middleware sqlite3 enhanced_sales.db "SELECT MIN(sale_date), MAX(sale_date) FROM fact_sales_pipeline;"
```

### Dates not persisting in query
- Open DevTools (F12) → Network → look for `/api/query` request
- Check if `date_from` and `date_to` are in request body
- Check server logs: `docker logs report-middleware | grep "custom date"`

### Reset button not working
- Clear browser cache (Ctrl+Shift+Del)
- Reload page (F5)
- Check browser console for errors (F12 → Console)

## Performance Impact

- ✅ **Minimal**: One additional API call on page load (`/api/date-limits`)
- ✅ **Query execution**: Potentially faster (explicit date range vs. parsing)
- ✅ **Database**: Single SQL query on startup: `SELECT MIN/MAX(sale_date)`

## Future Enhancements

1. **Preset buttons**: "Last 7 days", "Last 30 days", "This month", "This year"
2. **Date range shortcuts**: Quick select on date picker
3. **Custom periods**: Allow users to save favorite date ranges
4. **Relative dates**: "90 days ago", "Start of year", etc.
5. **Mobile optimization**: Improved mobile date picker UI

## Questions?

- Check [QUICK_START.md](QUICK_START.md) for deployment help
- Review [DEVELOPMENT.md](DEVELOPMENT.md) for local testing
- See [webapp/server.py](webapp/server.py) for API implementation
- Check [web/index.html](web/index.html) for UI code

---

**Deployment Status**: Ready for production deployment to Lightsail instance.
