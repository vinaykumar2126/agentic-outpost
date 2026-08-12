"""Golden dataset for the EventRanker eval.

Two sources of examples:
  1. REAL events pulled from events.db — thin descriptions and all, because that's
     exactly what the ranker sees in production.
  2. ADVERSARIAL hand-written events designed to probe known failure modes:
     keyword bait ("AI" in the title of a non-AI event), rubric edge cases, and
     the networking bonus rule.

Labels are BANDS (min_score, max_score), not exact scores — "did an agentic-AI
event land in 9-10?" is answerable; "is 7.5 vs 8.0 correct?" is not. Bands were
assigned by hand against the rubric in event_ranker.SYSTEM_PROMPT, deliberately
NOT copied from the model's own historical scores (that would make the eval
circular: the model grading its own homework).
"""

# fmt: off
GOLDEN_EXAMPLES = [
    # ── Real events from events.db ───────────────────────────────────────────
    {
        "inputs": {
            "title": "AWS Partner Showcase Extended (SF) - Agentic AI in Production with MongoDB Mastra",
            "description": "Experts from AWS, MongoDB and Mastra demonstrate how to build "
                           "production-ready agentic AI systems from code to deployment. Live "
                           "demonstrations and technical deep dives.",
            "organizer": "AICamp",
        },
        "outputs": {"min_score": 8.5, "max_score": 10.0,
                    "note": "Agentic AI in production — the rubric's own 9-10 example."},
    },
    {
        "inputs": {
            "title": "AI meetup (SV) for Securing Coding Agents",
            "description": "Deep dive tech talks on AI, GenAI, LLMs and Agents, hands-on code labs, "
                           "workshops, and networking with speakers and fellow developers. "
                           "In collaboration with Workato and Docker.",
            "organizer": "AICamp",
        },
        "outputs": {"min_score": 7.0, "max_score": 9.5,
                    "note": "Agent-focused engineering content + hands-on labs."},
    },
    {
        "inputs": {
            "title": "Show & Tell: AI for GTM @Notion with Baseten, Cognition and Samsara",
            "description": "Show & Tell: AI for GTM @Notion with Baseten, Cognition and Samsara",
            "organizer": "Mada Seghete",
        },
        "outputs": {"min_score": 4.0, "max_score": 7.0,
                    "note": "Hard case: big AI names but GTM/business focus, not engineering depth. "
                            "Production model has historically scored this 9.0 — likely overrated."},
    },
    {
        "inputs": {
            "title": "Robotics × Physical AI Founder-Investor Summit",
            "description": "Robotics × Physical AI Founder-Investor Summit",
            "organizer": "Sonia Chen",
        },
        "outputs": {"min_score": 4.0, "max_score": 7.0,
                    "note": "AI field but founder/investor audience, not AI engineering."},
    },
    {
        "inputs": {
            "title": "SF AI Code And Coffee Sunday July 26th!",
            "description": "SF AI Code And Coffee Sunday July 26th!",
            "organizer": "John Komarnicki",
        },
        "outputs": {"min_score": 5.0, "max_score": 8.0,
                    "note": "Casual AI builder coworking — moderately-to-highly relevant."},
    },
    {
        "inputs": {
            "title": "Durable Multimodal AI Meetup with HeyGen, Vapi, and Modal",
            "description": "Durable Multimodal AI Meetup with HeyGen, Vapi, and Modal",
            "organizer": "Modal Labs",
        },
        "outputs": {"min_score": 6.0, "max_score": 8.5,
                    "note": "Production AI infra companies presenting — 7-8 tier."},
    },
    {
        "inputs": {
            "title": "THE SF DATABASE MEETUP",
            "description": "THE SF DATABASE MEETUP",
            "organizer": "Victoria Liao",
        },
        "outputs": {"min_score": 2.0, "max_score": 5.0,
                    "note": "Infra-adjacent but not AI."},
    },
    {
        "inputs": {
            "title": "AI x Biosecurity — LatchBio Benchmark Launch",
            "description": "AI x Biosecurity — LatchBio Benchmark Launch",
            "organizer": "Harmon Bhasin",
        },
        "outputs": {"min_score": 3.0, "max_score": 6.0,
                    "note": "AI applied to a niche domain; no engineering-career relevance."},
    },
    {
        "inputs": {
            "title": "ElevenLabs x Sauna Hack Night",
            "description": "ElevenLabs x Sauna Hack Night",
            "organizer": "Sauna",
        },
        "outputs": {"min_score": 3.5, "max_score": 6.5,
                    "note": "AI company hack night, but zero detail to judge depth."},
    },
    {
        "inputs": {
            "title": "Mini BattleBots Tournament",
            "description": "Mini BattleBots Tournament",
            "organizer": "Adam Chan",
        },
        "outputs": {"min_score": 0.0, "max_score": 3.5,
                    "note": "Hobby robotics, not AI."},
    },
    {
        "inputs": {
            "title": "World Cup Watch Party: Semi-finals",
            "description": "World Cup Watch Party: Semi-finals",
            "organizer": "Kathy Wang",
        },
        "outputs": {"min_score": 0.0, "max_score": 2.0,
                    "note": "Unambiguously non-tech."},
    },
    {
        "inputs": {
            "title": "How to Break into SF as an Immigrant Founder",
            "description": "How to Break into SF as an Immigrant Founder",
            "organizer": "Founders on Tap",
        },
        "outputs": {"min_score": 0.5, "max_score": 3.5,
                    "note": "General founder content, no AI."},
    },
    {
        "inputs": {
            "title": "20th Oakland Hardware Meetup - Demo Night!",
            "description": "20th Oakland Hardware Meetup - Demo Night!",
            "organizer": "Kyle Valiton",
        },
        "outputs": {"min_score": 1.0, "max_score": 4.0,
                    "note": "General tech demo night."},
    },

    # ── Adversarial hand-written cases ───────────────────────────────────────
    {
        "inputs": {
            "title": "Multi-Agent Systems in Production: LangGraph + Bedrock AgentCore deep dive",
            "description": "Engineers from three companies walk through their production multi-agent "
                           "architectures: orchestration, memory, eval pipelines, and failure recovery. "
                           "Code walkthroughs included.",
            "organizer": "SF Agentic AI Builders",
        },
        "outputs": {"min_score": 9.0, "max_score": 10.0,
                    "note": "Textbook 9-10: agentic, production, hands-on."},
    },
    {
        "inputs": {
            "title": "AI-Powered Web3 Launchpad: Pitch Your AI Token",
            "description": "Founders pitch AI-branded crypto tokens to investors. Network with Web3 "
                           "VCs. $50 entry includes two drinks.",
            "organizer": "Crypto Growth Labs",
        },
        "outputs": {"min_score": 0.0, "max_score": 3.0,
                    "note": "Keyword bait: 'AI' in title, zero AI engineering content."},
    },
    {
        "inputs": {
            "title": "Intro to Excel for Business Analysts",
            "description": "Pivot tables, VLOOKUP, and dashboards for absolute beginners.",
            "organizer": "SF Career Center",
        },
        "outputs": {"min_score": 0.0, "max_score": 2.0,
                    "note": "Clean negative control."},
    },
    {
        "inputs": {
            "title": "ML Paper Reading Group: 'Attention Is All You Need' Retrospective",
            "description": "We reread the 2017 transformer paper and discuss what held up. "
                           "Academic discussion, all levels welcome.",
            "organizer": "Bay Area ML Study Group",
        },
        "outputs": {"min_score": 3.0, "max_score": 6.0,
                    "note": "Research discussion — AI/ML content without production/agentic focus."},
    },
    {
        "inputs": {
            "title": "AI Engineer Career Night: 1:1 with Hiring Managers",
            "description": "Speed-networking format: fifteen 1:1 conversations with hiring managers "
                           "and senior AI engineers from SF startups actively hiring for AI Engineer "
                           "and agent-infrastructure roles.",
            "organizer": "AI Talent Collective",
        },
        "outputs": {"min_score": 8.5, "max_score": 10.0,
                    "note": "Career development + explicit 1:1 networking bonus rule."},
    },
    {
        "inputs": {
            "title": "Vibe Coding 101: Build Your First Website with ChatGPT",
            "description": "No coding experience needed! Use ChatGPT to make a personal website "
                           "in one evening.",
            "organizer": "TechBridge Beginners",
        },
        "outputs": {"min_score": 1.5, "max_score": 4.5,
                    "note": "Uses AI, but consumer-level; no engineering depth."},
    },
    {
        "inputs": {
            "title": "Kubernetes for GenAI: Serving LLMs at Scale",
            "description": "Platform engineers share GPU scheduling, vLLM deployment patterns, "
                           "autoscaling inference workloads, and cost tuning on K8s.",
            "organizer": "Cloud Native SF",
        },
        "outputs": {"min_score": 6.5, "max_score": 9.0,
                    "note": "AI infrastructure / production deployment — 7-8 tier."},
    },
    {
        "inputs": {
            "title": "Sound Healing & Meditation with AI-Generated Soundscapes",
            "description": "A relaxing evening of guided meditation accompanied by ambient music "
                           "generated with AI tools.",
            "organizer": "Mindful SF",
        },
        "outputs": {"min_score": 0.0, "max_score": 3.0,
                    "note": "Keyword bait: AI-flavored wellness, not a tech event."},
    },
]
# fmt: on

