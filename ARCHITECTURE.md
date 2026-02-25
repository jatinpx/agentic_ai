# Phase 1 MVP Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DAILY AUTOMATION PIPELINE                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      SCHEDULER (APScheduler)                        │   │
│  │                   Triggers daily at 08:00 UTC                       │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                          │
│                                 ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              ORCHESTRATOR (orchestrator.py)                         │   │
│  │          Coordinates pipeline execution and error handling          │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                          │
│        ┌────────────────────────┼────────────────────────────┐             │
│        ▼                        ▼                            ▼             │
│   ┌─────────────┐          ┌──────────────┐         ┌────────────────┐   │
│   │NEWS AggREG  │          │TOPIC RANKER  │         │TELEGRAM ADAPTER│   │
│   │─────────────│          │──────────────│         │────────────────│   │
│   │• Tavily     │   News   │• Score       │ Ranked │• Format msg    │   │
│   │• DuckDuckGo │ ------→  │  virality    │ topics │• Send buttons  │   │
│   │• NewsAPI    │  Items   │• Score       │ -----→ │• Parse clicks  │   │
│   │• HackerNews │          │  relevance   │        │                │   │
│   │             │          │• Gen angles  │        │                │   │
│   └─────────────┘          └──────────────┘        └────────────────┘   │
│        │                                            │                      │
│        └────────────────────┬─────────────────────────┘                   │
│                             │                                             │
│                             ▼                                             │
│        ┌────────────────────────────────────────────────────────┐         │
│        │             POSTGRESQL DATABASE                        │         │
│        │  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐│         │
│        │  │ daily_        │  │ chat_       │  │ automation_    ││         │
│        │  │ suggestions   │  │ interactions│  │ posts          ││         │
│        │  │ (topics sent) │  │ (audit log) │  │ (drafts+publd) ││         │
│        │  └──────────────┘  └─────────────┘  └────────────────┘│         │
│        │  ┌──────────────────────────────────────────────────────┐│       │
│        │  │ users (automation profiles, interests, telegram_id)  ││       │
│        │  └──────────────────────────────────────────────────────┘│       │
│        └────────────────────────────────────────────────────────┘         │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           CHAT INTERACTION FLOW                             │
│                                                                             │
│  USER'S TELEGRAM APP                                                       │
│  ┌─────────────────────────────┐                                          │
│  │ 📱 Receives message:        │                                          │
│  │  "📰 Today's Topics:"       │                                          │
│  │  [1. AI Breakthrough]       │ Button                                   │
│  │  [2. Startup Funding]       │ Clicks                                   │
│  │  [3. Security Crisis]       │ ──────────┐                             │
│  │  ...                        │           │                             │
│  │  [✅ Done Selecting]        │           ▼                             │
│  └─────────────────────────────┘      POST /automation/telegram/webhook  │
│                                              │                            │
│                                              ▼                            │
│        ┌────────────────────────────────────────────────────────────┐    │
│        │           CHAT HANDLERS (handlers.py)                      │    │
│        │  ┌─────────────────────────────────────────────────────┐   │    │
│        │  │ ChatStateManager                                    │   │    │
│        │  │ • Track user selection state                        │   │    │
│        │  │ • Route callback_queries to handlers                │   │    │
│        │  │ • Update selected_topic_ids                         │   │    │
│        │  │ • Transition state machine                          │   │    │
│        │  └─────────────────────────────────────────────────────┘   │    │
│        └────────────────────────────────────────────────────────────┘    │
│                         User Selects Topics                                │
│                         ┌─────────────────────┐                           │
│                         ▼                     ▼                           │
│            ┌────────────────────┐   ┌─────────────────┐                 │
│            │DB Store Selection  │   │Trigger Generation(TODO)             │
│            │ ├─ topic_ids       │   │ ├─ Call LangGraph agent           │
│            │ ├─ timestamp       │   │ ├─ Generate post draft            │
│            │ └─ status='selected'   │ └─ Send for approval              │
│            └────────────────────┘   └─────────────────┘                 │
│                                              │                           │
│                                    User Reviews Post                      │
│                                    ┌────────┴────────┐                  │
│                                    ▼                 ▼                  │
│                        [✅ Approve] ... [❌ Reject]                      │
│                                    │                 │                  │
│                ┌───────────────────┼─────────────────┘                  │
│                ▼                   ▼                                    │
│        ┌──────────────┐    ┌──────────────┐                           │
│        │ Publish to   │    │ Log Reject   │                           │
│        │ LinkedIn API │    │ Prompt retry │                           │
│        │ (TODO)       │    │ tomorrow     │                           │
│        └──────────────┘    └──────────────┘                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE LAYER ARCHITECTURE                        │
│                                                                             │
│  EXTERNAL APIs                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │  Tavily  │  │DuckDuckGo│  │ NewsAPI  │  │HackerNews│                   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│       │             │             │             │                         │
│       └─────────┬───┴─────────┬───┴─────────┬───┘                         │
│                 ▼                             │                           │
│         ┌──────────────────┐                 │                           │
│         │ NewsAggregator   │                 │                           │
│         │ • Multiple src   │                 │                           │
│         │ • Dedup by title │                 │                           │
│         │ • Categorize     │                 │                           │
│         └──────────┬───────┘                 │                           │
│                    │                         │                           │
│                    ▼                         │                           │
│         ┌──────────────────┐                 │                           │
│         │ TopicRanker      │ Ollama ---┐     │                           │
│         │ • Virality score │      LLM  │     │                           │
│         │ • Relevance      │          │     │                           │
│         │ • Gen angles     │◄─────────┘     │                           │
│         └──────────┬───────┘                │                           │
│                    │                        │                           │
│                    ▼                        ▼                           │
│         ┌──────────────────────────────────────────┐                   │
│         │ Orchestrator                             │                   │
│         │ • Coordinate pipeline steps              │                   │
│         │ • Handle user flows                      │                   │
│         │ • Error recovery                         │                   │
│         └──────────┬───────────────────────────────┘                   │
│                    │                                                   │
│    ┌───────────────┼───────────────┐                                  │
│    ▼               ▼               ▼                                  │
│ Database      TelegramAdapter    LinkedInAgent(TODO)                 │
│ • CRUD        • Format msgs      • Generate posts                    │
│ • Queries     • Send buttons     • Publish to API                    │
│ • Logging     • Parse clicks     │                                   │
│               │                                                       │
│               ▼                                                       │
│         TelegramBotAPI                                               │
│         (python-telegram-bot)                                        │
│                                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW: News to Post                             │
│                                                                             │
│  Step 1: NEWS AGGREGATION                                                  │
│  ┌─────────────┐     ┌──────────────────────────────────────┐             │
│  │ 5 APIs Called  │ → │ 100+ articles fetched                │             │
│  └─────────────┘     │ • URL, title, snippet, date, source   │             │
│                      └──────────────┬───────────────────────┘             │
│                                     │                                    │
│                                     ▼                                    │
│  Step 2: DEDUPLICATION                                                  │
│  ┌─────────────────────────────────────────────────────────┐             │
│  │ Input: 100 articles                                      │             │
│  │ Output: ~50 unique (deduplicated by headline)            │             │
│  └──────────────────────┬──────────────────────────────────┘             │
│                         │                                               │
│                         ▼                                               │
│  Step 3: RANKING (Per User)                                            │
│  Input: 50 news + User interests=['AI', 'Startups']                    │
│    ┌────────────────────────────────────┐                              │
│    │ For each article:                  │                              │
│    │ • Calc virality (0-100)           │                              │
│    │ • Calc relevance (0-100)          │                              │
│    │ • Combined = 60% virality         │                              │
│    │          + 40% relevance          │                              │
│    │ • Gen 3-5 LinkedIn angles         │                              │
│    └────────────────────────────────────┘                              │
│  Output: Top 5 ranked topics with full metadata                       │
│                         │                                               │
│                         ▼                                               │
│  Step 4: TELEGRAM MESSAGING                                            │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ Format:                                                  │           │
│  │ 📰 Today's Tech Topics                                  │           │
│  │ 1. AI Breakthrough (Score: 92/100)                      │           │
│  │    Category: AI/ML | Virality: 95 | Relevance: 89      │           │
│  │    Angles: ["Why this matters for enterprises", ...]   │           │
│  │    [Select Topic #1]                                    │           │
│  │ ...                                                      │           │
│  │ [✅ Done Selecting]                                     │           │
│  └─────────────────────────────────────────────────────────┘           │
│                         │                                               │
│                         ▼                                               │
│  Step 5: USER INTERACTION                                              │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │ User selects topic(s) by clicking buttons               │           │
│  │ Callback query stored:                                  │           │
│  │ • selected_topic_ids = [id1, id2, ...]                 │           │
│  │ • state.status = 'selection_made'                       │           │
│  │ Store in chat_interactions table                        │           │
│  └─────────────┬───────────────────────────────────────────┘           │
│                │                                                       │
│                ▼                                                       │
│  (Step 6-7: POST GENERATION & PUBLISHING - TODO in Phase 2)           │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## File Directory Structure

```
backend/
├── services/
│   ├── __init__.py
│   ├── news_aggregator.py       # 290 lines
│   ├── topic_ranker.py          # 383 lines
│   ├── scheduler_service.py     # 238 lines
│   ├── orchestrator.py          # 242 lines
│   └── ... (existing services)
│
├── chat/
│   ├── __init__.py
│   ├── models.py                # 98 lines
│   ├── telegram_adapter.py      # 365 lines
│   └── handlers.py              # 339 lines
│
├── db/
│   ├── automation_db.py         # 315 lines
│   └── migrations/
│       └── 003_automation_tables.py  # 126 lines
│
├── brain/linkedin/
│   ├── routes.py                # (existing)
│   └── automation_routes.py     # 354 lines (NEW)
│
├── main.py                      # (modified)
├── requirements.txt             # (updated)
└── ... (existing files)
```

## Statistics

- **Total New Files**: 10
- **Total New Lines of Code**: ~2,700
- **Database Tables**: 4 (users, daily_suggestions, chat_interactions, automation_posts)
- **API Endpoints**: 10+ (trigger, jobs, scheduler, user profile, telegram webhook, debug)
- **External Integrations**: 5+ (Tavily, DuckDuckGo, NewsAPI, HackerNews, Telegram)
- **Estimated Daily Users at Launch**: ~50-100
- **Scalability**: Can handle 500+ users with optimizations (Redis, async batch)

---

**Visual Reference**:
- Daily Cycle: 8 AM UTC → News gather → Rank → Send → Wait for user → (Phase 2) Generate → Approve → Publish
- Cycle Time: ~60 seconds for 50 users
- Peak Load: ~500 API calls (depending on user count)
