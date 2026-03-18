# Untitled

**Context Package for Personalization Email Generator:**Company Overview**KiwiQ AI** - Experimentation infrastructure for marketing (starting with AI visibility content)

- **Stage:** Private beta, 5 B2B customers at $10K ACV
- **Ask:** $500K for 12-month runway to $100K MRR
- **Founded:** Early 2024 (started building January 2024)
- **GTM:** Organic word-of-mouth with YC-backed dev tools, vertical AI startups, deep tech founders

Core ProblemB2B brands are losing AI visibility wars. 89% of B2B buyers use generative AI in purchase process (Forrester). When prospects ask ChatGPT "What's the best [category] tool?", brands either show up or don't exist. Most brands have zero control over AI-generated positioning. The lever: strategic first-party content that builds domain authority AI platforms cite.The Solution (Current → Vision)**Now (ContentQ):** AI visibility content platform that operates as "experimentation infrastructure" - not just automation. Multi-agent system where Research, Strategy, Copywriter, and Analytics agents + human stakeholders (CEO, PM, Marketing) share persistent memory. CEO voice notes auto-update knowledge base. Performance learnings feed back into strategy. System gets smarter with every experiment.**Unique Value:** Out-competing content agencies with 10% of the human hours by putting intelligence in the system, not dependent on senior talent.**Vision:** Build what HubSpot built internally (100K+ annual content experiments) as an open platform for any marketing team. Full experimentation cycle: design using accumulated intelligence → execute through multi-agent orchestration → interpret results → feed learnings back. Expand from content to product launches, demand gen, competitive intelligence.Technical MoatBuilt **TeamGraph** - proprietary infrastructure for agentic orchestration with shared memory across full experiment lifecycle. Why they had to build from scratch:

- LangChain/LangGraph break at production scale (abstractions leak, checkpointing bottlenecks, complexity explodes with multiple agents)
- n8n/Relevance AI lack persistent memory across workflows and require humans to orchestrate
- Existing tools are workflow automation, not experimentation infrastructure

Key innovation: Human input trains the system on company-specific voice/audience, but system doesn't need humans to ferry context or orchestrate workflows. Solves the handoff problem where CEOs nail positioning on calls but insights get watered down by the time they reach final drafts.Founders**Founder A** - Technical co-founder

- Ex-BigTech ML Lead
- Built multi-agent systems processing billions of queries
- Deep expertise: LLMs + knowledge graphs at production scale
- Spent 5 months rebuilding multi-agent infrastructure from first principles after LangChain/LangGraph failed

**Founder B** - Business co-founder

- Ex-BigTech Product Lead
- Built marketing experimentation tools at YC startup where enterprises paid millions/year - saw firsthand the ROI of systematic marketing experiment infrastructure
- Worked as a content marketer for 8 months with 12+ B2B founders, and learned the importance of running high-quality content experiments and the limitations of existing AI marketing tools and AI workflow automation tools

**Team Strength:** Rare combination of production-scale ML infrastructure expertise + deep market intimacy from operating in the domain.Why Now

- Models dramatically improved in 2024 (function calling 70%→95%+, reliable long context, structured output works)
- But gaps remain: LangChain/LangGraph still break, no one solved multi-agent orchestration with persistent memory, marketing lacks systematic experimentation infrastructure
- AI visibility shift is urgent and accelerating (Gartner: AI agents will make 15% of day-to-day work decisions by 2028)

Key Personalizations to Research

- **BigTech connections:** Founder A ex-BigTech (ML team)
- **BigTech connections:** Founder B ex-BigTech
- **YC connections:** Founder B worked at YC startup, currently working with YC-backed companies
- **AI/ML infrastructure thesis:** Multi-agent systems, LLM infrastructure, production ML
- **Marketing tech thesis:** Experimentation platforms, marketing operations, GTM infrastructure
- **B2B SaaS thesis:** Particularly dev tools, vertical AI, technical products
- **Content/AI visibility focus:** Investors thinking about LLM discovery, AI-native GTM
- **Agency-to-product transitions:** Experience building in the problem space first
- **Developer tools background:** Both founders from product/ML roles at major tech companies
