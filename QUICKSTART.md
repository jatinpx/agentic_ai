# Phase 1 MVP - Quick Start Guide

## Prerequisites

### 1. System Requirements
- Python 3.11+
- PostgreSQL 14+
- Ollama (for local LLM)
- Linux/macOS terminal

### 2. Environment Setup

```bash
# Navigate to backend
cd /home/tuf/work/cog-assignments/aiml/AI/autonomus-ai-employee/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables

Create `.env` file in backend directory:

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_employee

# Telegram (Get from BotFather on Telegram)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret_here

# News APIs
TAVILY_API_KEY=your_tavily_api_key
NEWSAPI_KEY=your_newsapi_key

# LLM
OLLAMA_BASE_URL=http://localhost:11434
```

### 4. Database Setup

```bash
# Create database (if not exists)
createdb -U postgres ai_employee

# Run migrations (migration script will run on app startup)
# Or manually:
python db/migrations/003_automation_tables.py
```

## Testing the Pipeline

### Test 1: Start the Backend

```bash
# From backend directory with venv activated
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
[Startup] Automation database tables initialized
[Startup] Scheduler started
[Startup] Daily news pipeline scheduled for 08:00 UTC
```

### Test 2: Manual News Aggregation

```bash
# In another terminal
curl http://localhost:8000/automation/debug/news

# Expected: JSON with 5-50 news items
```

### Test 3: Topic Ranking

```bash
curl "http://localhost:8000/automation/debug/topics?interests=AI,Startups"

# Expected: Ranked topics with scores and content angles
```

### Test 4: Trigger Full Pipeline

```bash
curl -X POST http://localhost:8000/automation/trigger-daily

# Expected: News → ranking → users notified (if automation_enabled=true)
```

### Test 5: Check Scheduler Status

```bash
curl http://localhost:8000/automation/jobs

# Expected: Job list with next run time
```

## Setting Up Telegram Bot (For Real Testing)

### Step 1: Create Telegram Bot

1. Open Telegram
2. Search for @BotFather
3. /newbot
4. Choose name (e.g., "AI Content Bot")
5. Copy token → paste into `.env` as `TELEGRAM_BOT_TOKEN`

### Step 2: Get Your User ID

```bash
# Message @userinfobot
# It will reply with your Telegram user_id (9 digits)
```

### Step 3: Enable Automation for Your User

```bash
# Create user in database
psql ai_employee

INSERT INTO users (telegram_user_id, automation_enabled, tech_interests)
VALUES (123456789, true, ARRAY['AI', 'Startups', 'Security']);

-- Replace 123456789 with your actual Telegram user_id
```

### Step 4: Configure Webhook (Optional, for Production)

For development, the bot can use polling instead of webhook. To use webhook:

```bash
# Set webhook URL (your server must be HTTPS + publicly accessible)
curl -X POST https://api.telegram.org/bot{TOKEN}/setWebhook \
  -F url=https://your-domain.com/automation/telegram/webhook
```

### Step 5: Trigger Pipeline

```bash
# Manually trigger to test without waiting 8 hours
curl -X POST http://localhost:8000/automation/trigger-daily

# Or wait for next 8 AM UTC if scheduler is running
```

You should receive a Telegram message with today's top 5 tech topics!

## Database Inspection

```bash
# Check users table
psql ai_employee
SELECT * FROM users;

# Check suggestions sent
SELECT * FROM daily_suggestions;

# Check interactions log
SELECT * FROM chat_interactions ORDER BY created_at DESC;

# Check published posts
SELECT * FROM automation_posts;
```

## Troubleshooting

### Issue: "telegram_user_id UNIQUE constraint failed"
**Fix**: User already exists. Update instead of creating:
```bash
UPDATE users SET automation_enabled = true WHERE telegram_user_id = 123456789;
```

### Issue: "No news items aggregated"
**Fix**: Check API keys and network:
```bash
# Test Tavily API
curl -X POST "https://api.tavily.com/search" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"your_key","query":"test"}'
```

### Issue: Ollama connection error
**Fix**: Make sure Ollama is running:
```bash
# Terminal 1
ollama serve

# Terminal 2
ollama run mistral
```

### Issue: Database connection refused
**Fix**: Check PostgreSQL is running:
```bash
psql -U postgres -d ai_employee -c "SELECT 1"
```

## Understanding the Flow

```
1️⃣ AGGREGATION PHASE (5-10 seconds)
   - Fetch from Tavily, DuckDuckGo, NewsAPI
   - Input: None
   - Output: 20-50 unique news articles

2️⃣ RANKING PHASE (2-5 seconds per user)
   - Score by virality + relevance
   - Generate content angles
   - Input: News items + user interests
   - Output: Top 5 ranked topics

3️⃣ TELEGRAM MESSAGING (1-2 seconds per user)
   - Format as Telegram message
   - Add topic selection buttons
   - Input: Ranked topics
   - Output: Telegram message sent

4️⃣ USER SELECTION (User interaction)
   - User clicks topic button(s)
   - Chat state updated
   - Input: User callback query
   - Output: Selected topic IDs in DB

5️⃣ POST GENERATION (TODO: Implement)
   - LangGraph agent generates post
   - Input: Selected topics
   - Output: Post draft

6️⃣ APPROVAL FLOW (TODO: Implement)
   - Send for user approval
   - User approves/rejects
   - On approve: publish to LinkedIn
```

## Performance Notes

### Single Daily Run (All Users)
- 50 users + 50 news items ≈ 30-60 seconds total
- Breakdown:
  - News aggregation: 10 sec
  - Ranking (50 users): 30-40 sec
  - Telegram send: 5-10 sec

### Scalability for Phase 2
- Use Redis for caching (avoid re-fetching news)
- Parallelize user ranking with asyncio
- Implement queue system for post generation

## Next Development Steps

1. ✅ News aggregation service
2. ✅ Topic ranking service  
3. ✅ Telegram messaging adapter
4. ✅ Chat state machine
5. ✅ Database schema
6. ⏳ **LangGraph post generation** ← Next
7. ⏳ LinkedIn publishing API
8. ⏳ WhatsApp integration
9. ⏳ Analytics dashboard
10. ⏳ User management UI

---

**Questions?** Check logs:
```bash
# Backend logs
tail -f logs/*.log

# SQLite logs (if using)
sqlite3 logs/automation.db "SELECT * FROM logs LIMIT 10;"
```

**Ready to test?** Start the backend and send your first `/automation/trigger-daily`! 🚀
