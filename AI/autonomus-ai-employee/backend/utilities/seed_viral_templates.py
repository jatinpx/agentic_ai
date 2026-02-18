"""
Seed script: Populate linkedin_viral_templates with known high-performing
hook patterns and post structures.

Run once:
    cd backend && python -m utilities.seed_viral_templates
"""

from db.linkedin_repo import create_linkedin_tables, insert_viral_template
from embeddings.embedder import embed_text


VIRAL_TEMPLATES = [
    # ========== TECH INSIGHTS ==========
    {
        "content": "I've been building software for 15 years.\n\nThe biggest lesson?\n\nThe best code is the code you don't write.\n\nEvery line you add is a line you maintain. Every abstraction you create is complexity someone inherits.\n\nThe senior engineers I respect most are the ones who push back and ask: do we actually need this?\n\nSimplicity is the ultimate sophistication in engineering.",
        "hook_pattern": "I've been [doing X] for [N] years. The biggest lesson?",
        "category": "tech_insights",
        "engagement_score": 9.2,
    },
    {
        "content": "Unpopular opinion: Most microservices architectures are just distributed monoliths with extra latency.\n\nIf your services can't be deployed independently, if they share a database, if changing one breaks three others...\n\nYou don't have microservices. You have a monolith with network calls.\n\nStart with a well-structured monolith. Split when you actually need to.\n\nAm I wrong?",
        "hook_pattern": "Unpopular opinion: [Bold contrarian statement]",
        "category": "tech_insights",
        "engagement_score": 8.8,
    },
    {
        "content": "The best engineers I've worked with all do something most people skip.\n\nThey read the error message.\n\nNot just glance at it. Actually read it. The whole thing.\n\n90% of debugging is reading what the system is literally telling you.\n\nThe other 10% is realizing you were looking at the wrong log file.",
        "hook_pattern": "The best [role]s I've worked with all do something most people skip.",
        "category": "tech_insights",
        "engagement_score": 8.5,
    },
    {
        "content": "AI won't replace programmers.\n\nBut programmers who use AI will replace programmers who don't.\n\nI've seen junior developers 3x their output using AI tools. Not by copy-pasting — by understanding what to ask and how to validate the output.\n\nThe skill isn't prompt engineering. It's knowing enough to spot when the AI is confidently wrong.\n\nThat's the new literacy.",
        "hook_pattern": "[X] won't replace [Y]. But [Y] who use [X] will replace [Y] who don't.",
        "category": "tech_insights",
        "engagement_score": 9.5,
    },
    # ========== CAREER ADVICE ==========
    {
        "content": "I got rejected from 47 companies before I got my first tech job.\n\nHere's what nobody tells you about job searching:\n\n1. Your resume gets 6 seconds of attention\n2. Referrals get 10x the callback rate\n3. The posted requirements are a wish list, not requirements\n4. Following up is not annoying — it's expected\n5. The best opportunities aren't posted anywhere\n\nThe job search is a skill. Treat it like one.",
        "hook_pattern": "I got rejected from [N] [things] before [success]. Here's what nobody tells you.",
        "category": "career_advice",
        "engagement_score": 9.0,
    },
    {
        "content": "Stop calling yourself a '10x engineer.'\n\nThe people who actually move the needle do something different.\n\nThey make the 10 engineers around them 2x better.\n\nThey write docs. They review PRs thoughtfully. They unblock people instead of hoarding context.\n\nImpact isn't about your output. It's about the system's output because you're in it.\n\nMultiply others, don't just multiply yourself.",
        "hook_pattern": "Stop calling yourself a '[trendy title].'",
        "category": "career_advice",
        "engagement_score": 8.7,
    },
    {
        "content": "Your manager doesn't owe you a promotion.\n\nBut they do owe you clarity.\n\n- Clear expectations for your level\n- Honest feedback on where you stand\n- A path forward — even if it's not straight up\n\nIf you're not getting these three things, you're not in a bad role. You're in a bad management relationship.\n\nHave the conversation. If it doesn't change, have the exit conversation.",
        "hook_pattern": "Your [person] doesn't owe you [expected thing]. But they do owe you [important thing].",
        "category": "career_advice",
        "engagement_score": 8.3,
    },
    # ========== HOT TAKES ==========
    {
        "content": "Hot take: Leetcode has nothing to do with being a good engineer.\n\nI've seen people ace every algorithm question and then write production code that crashes under 100 concurrent users.\n\nKnowing how to reverse a linked list doesn't mean you can design a system that scales.\n\nWe're filtering for puzzle solvers when we need system thinkers.\n\nThe interview process is broken. We all know it. Why do we keep playing the game?",
        "hook_pattern": "Hot take: [Widely practiced thing] has nothing to do with [actual goal].",
        "category": "hot_takes",
        "engagement_score": 9.1,
    },
    {
        "content": "Your startup doesn't need AI.\n\nI said what I said.\n\n80% of AI features I see in products are solving non-problems with expensive solutions.\n\nBefore you add an AI chatbot, ask:\n- Can a search bar solve this?\n- Would a better UX fix this?\n- Is anyone actually asking for this?\n\nAI is a tool, not a business strategy.\n\nAgree or disagree?",
        "hook_pattern": "Your [thing] doesn't need [trendy tech]. I said what I said.",
        "category": "hot_takes",
        "engagement_score": 8.9,
    },
    {
        "content": "Remote work isn't the future.\n\nAsynchronous work is.\n\nThe problem was never where you sit. It was always about synchronous meetings destroying deep work.\n\nYou can be in an office and be productive if meetings are async.\nYou can be remote and unproductive if your calendar is packed.\n\nLocation is a distraction from the real conversation.",
        "hook_pattern": "[Popular opinion] isn't the future. [Deeper insight] is.",
        "category": "hot_takes",
        "engagement_score": 8.6,
    },
    # ========== FOUNDER STORIES ==========
    {
        "content": "2 years ago I quit my job with no plan.\n\nNo savings runway. No co-founder. No customers.\n\nJust an idea and the conviction that the timing was right.\n\nMonth 1: Built an MVP in my apartment\nMonth 3: First paying customer ($49/mo)\nMonth 6: Ramen profitable\nMonth 12: Hired employee #1\nMonth 24: 7-figure ARR\n\nWas I reckless? Maybe.\nWould I do it again? Absolutely.\n\nThe risk of starting is always smaller than the regret of not trying.",
        "hook_pattern": "[Time] ago I [brave/reckless decision] with no [safety net].",
        "category": "founder_stories",
        "engagement_score": 9.3,
    },
    {
        "content": "We almost shut down our startup. Twice.\n\nThe first time, we ran out of money 3 weeks before our first enterprise deal closed.\nThe second time, our entire platform went down for 16 hours on the day of a demo.\n\nBoth times, we thought it was over.\n\nBut here's what I learned: startups don't die from one bad event. They die from founders who give up after one bad event.\n\nResilience isn't a personality trait. It's a practice.",
        "hook_pattern": "We almost [dramatic failure] our [company/project]. [Frequency].",
        "category": "founder_stories",
        "engagement_score": 8.8,
    },
    # ========== INDUSTRY TRENDS ==========
    {
        "content": "Every SaaS company is about to face an existential question:\n\nWhy should I pay $99/month for your tool when an AI agent can do the same thing for $0.02 per task?\n\nThe SaaS model works because software is easier than hiring people.\n\nBut AI agents are easier than software.\n\nThe companies that survive will be the ones that sell outcomes, not features.\n\nThe next 3 years will be brutal for anyone who can't answer: what do we do that AI can't?",
        "hook_pattern": "Every [industry/company type] is about to face an existential question.",
        "category": "industry_trends",
        "engagement_score": 9.4,
    },
    {
        "content": "The developer tools market is about to collapse.\n\nHere's why:\n\n1. AI can generate boilerplate — killing low-code tools\n2. AI can debug — killing monitoring dashboards\n3. AI can deploy — killing DevOps platforms\n\nBut here's the twist: the tools that survive will be the ones AI uses.\n\nThe customer isn't the developer anymore. The customer is the AI agent.\n\nBuild for the agent, not the engineer.",
        "hook_pattern": "The [specific market] is about to collapse. Here's why.",
        "category": "industry_trends",
        "engagement_score": 8.7,
    },
    {
        "content": "In 2025, the most valuable skill isn't coding.\n\nIt's taste.\n\nAI can write code. AI can design UIs. AI can generate content.\n\nBut AI can't tell you what's worth building.\n\nThe people who thrive will be the ones who can look at 100 options and pick the right one.\n\nTaste is knowing what to say no to.\nTaste is an engineering skill now.",
        "hook_pattern": "In [year], the most valuable skill isn't [expected]. It's [unexpected].",
        "category": "industry_trends",
        "engagement_score": 9.1,
    },
    # ========== LEADERSHIP ==========
    {
        "content": "The best meeting I ever attended was the one that got cancelled.\n\nI'm not joking.\n\nThe organizer realized halfway through prep that the decision could be made in a 3-line Slack message.\n\nSo they sent the message, cancelled the meeting, and gave 8 people 30 minutes back.\n\nThat's leadership.\n\nNot filling calendars. Protecting time.\n\nHow many meetings on your calendar this week could be a message?",
        "hook_pattern": "The best [X] I ever [experienced] was the one that [unexpected twist].",
        "category": "leadership",
        "engagement_score": 8.9,
    },
    {
        "content": "I fired our highest performer last quarter.\n\nBrilliant engineer. 10x output. Shipped features faster than anyone.\n\nBut left a trail of burned bridges, broken trust, and demoralized teammates.\n\nThe math is simple:\n1 brilliant jerk = 3 good people quitting.\n\nCulture isn't a poster on the wall. It's who you're willing to let go.\n\nThe team's morale improved within 2 weeks. Output went UP, not down.",
        "hook_pattern": "I [controversial action] our [impressive person] last [time period].",
        "category": "leadership",
        "engagement_score": 9.0,
    },
    # ========== LEARNING ==========
    {
        "content": "I learned more in 6 months of building side projects than in 4 years of computer science.\n\nNot because college was bad. But because building forces decisions that textbooks skip.\n\nWhich database? How to deploy? What happens when real users hit your app at 2 AM?\n\nTheory teaches you why things work.\nBuilding teaches you why things break.\n\nYou need both. But if you're only doing one, build.",
        "hook_pattern": "I learned more in [short time] of [doing] than [long time] of [studying].",
        "category": "learning",
        "engagement_score": 8.4,
    },
    {
        "content": "Read less. Build more.\n\nI used to read 3 tech books a month and ship nothing.\n\nNow I read 3 chapters, build something with what I learned, then move on.\n\nThe difference?\n\nKnowledge without application is trivia.\nKnowledge with application is skill.\n\nStop collecting bookmarks. Start collecting shipped projects.",
        "hook_pattern": "[Do less popular thing]. [Do more unpopular thing].",
        "category": "learning",
        "engagement_score": 8.2,
    },
]


def seed():
    """Seed all viral templates into the database."""
    print("Ensuring LinkedIn tables exist...")
    create_linkedin_tables()

    print(f"Seeding {len(VIRAL_TEMPLATES)} viral templates...")
    success = 0
    failed = 0

    for i, template in enumerate(VIRAL_TEMPLATES, 1):
        try:
            print(f"  [{i}/{len(VIRAL_TEMPLATES)}] {template['category']}: {template['hook_pattern'][:50]}...")
            embedding = embed_text(template["content"])
            insert_viral_template(
                content=template["content"],
                hook_pattern=template["hook_pattern"],
                category=template["category"],
                embedding=embedding,
                engagement_score=template["engagement_score"],
            )
            success += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print(f"\nDone. {success} seeded, {failed} failed.")


if __name__ == "__main__":
    seed()
