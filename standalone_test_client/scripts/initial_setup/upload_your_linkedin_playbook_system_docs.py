"""
Simple LinkedIn Playbook System Document Uploader for Markdown Content

Instructions:
1. Add your documents to the DOCUMENTS list below
2. Each document needs a 'name' and 'markdown_content'
3. Paste your markdown content directly into the 'markdown_content' field
4. Run: python scripts/initial_setup/upload_your_linkedin_playbook_system_docs.py
"""

import asyncio
import logging
from kiwi_client.customer_data_client import CustomerDataTestClient
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.schemas.workflow_api_schemas import CustomerDataUnversionedCreateUpdate

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# CUSTOMIZE THIS: Add your markdown documents here
DOCUMENTS = [
    {
        'name': 'LinkedIn Play 1: The Transparent Founder Journey',
        'markdown_content': {"data": """## **LinkedIn Play 1: The Transparent Founder Journey**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Transparent Founder Journey - Build trust and connection by sharing the real, unvarnished founder experience.

**Strategic Theory**: Radical transparency creates parasocial relationships that convert to business value. By sharing real metrics, mistakes, and lessons, you build an audience that roots for your success. This play works because it satisfies the human desire to see behind the curtain while positioning you as an authentic, relatable leader. Success comes from consistent, honest sharing that makes your audience feel invested in your journey.

**Expected Timeline**: Next 3 months - establish transparent founder voice, begin building engaged following, and create initial transparency-driven connections.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Transparent Founder Journey approach. Focus on authentic founder experiences, challenges, and lessons. Consider their company stage ({COMPANY_STAGE}), industry challenges, and personal founder journey. Themes should cover: 1) Metrics transparency and business reality sharing, 2) Mistake admission and learning documentation, 3) Decision-making process and rationale sharing, 4) Personal founder challenges and growth experiences, 5) Team building and leadership lesson sharing. Each theme should create authentic connection through vulnerability and transparency. Format: Theme name + 2-3 sentence description emphasizing authentic founder storytelling and transparent leadership.
```

**Content Types**:
- **Weekly Metrics Updates**: Regular business performance and reality sharing
- **Mistake Admission Posts**: Honest failure analysis and learning extraction
- **Decision Transparency**: Behind-the-scenes choice-making and rationale
- **Personal Challenge Sharing**: Founder mental health, growth, and struggle content
- **Team Building Stories**: Hiring, firing, and leadership lesson documentation
- **Fundraising Reality**: Investor meeting outcomes, rejection analysis, and process insights
- **Small Win Celebrations**: Milestone achievement and gratitude expression
- **Learning Moment Documentation**: Real-time insight and development sharing
- **Board Meeting Insights**: Governance reality and strategic decision sharing
- **Industry Reality Checks**: Market condition impact and adaptation strategies

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Transparent Founder Journey. Target founder community, startup journey, and entrepreneurship content discovery. Focus on authentic founder content optimization. Generate: 1) LinkedIn keyword integration around "founder journey", "startup transparency", "entrepreneur lessons", "building in public", "{industry} founder" - weave naturally into personal storytelling, 2) Content structure optimization: Hook-heavy openings, story narrative flow, lesson extraction, community engagement questions, 3) Engagement optimization: Vulnerability-driven engagement, comment community building, story continuation techniques, 4) Network building: Founder community engagement, transparency advocate connection, authentic leadership positioning, 5) Content amplification: Story sharing across transparency advocates, founder community amplification, authentic content network growth. Goal is to build authentic founder brand through transparent storytelling that attracts community investment.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Follower growth rate and engagement quality (comments, meaningful interactions)
- Inbound opportunities (investor, advisor, talent, customer inquiries from content)
- Community building (transparent founder network development)
- Business impact (pipeline, partnerships, team building from transparency)

**Secondary Metrics**:
- Content sharing and amplification rates
- Speaking opportunity generation from thought leadership
- Media coverage and interview opportunities
- Talent attraction and quality improvement
- Customer trust and brand affinity development
"""}
    },
    {
        'name': 'LinkedIn Play 2: The Teaching CEO',
        'markdown_content': {"data": """## **LinkedIn Play 2: The Teaching CEO**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Teaching CEO - Establish expertise by teaching complex concepts in accessible ways.

**Strategic Theory**: Teaching builds authority while providing value. This play positions you as the professor of your niche, breaking down complex topics into digestible insights. It works by demonstrating mastery through the ability to simplify and explain clearly. Success comes from consistent educational content that makes you the go-to source for understanding complex topics in your domain.

**Expected Timeline**: Next 3 months - establish teaching authority, develop initial educational content series, and begin building learning-focused community.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Teaching CEO approach. Focus on their domain expertise ({EXPERTISE_DOMAIN}) and ability to educate their audience. Consider their unique insights, industry knowledge, and teaching opportunities. Themes should cover: 1) Complex concept simplification and education, 2) Framework development and methodology sharing, 3) Industry analysis and trend explanation, 4) Skill development and capability building guidance, 5) Historical context and evolution pattern teaching. Each theme should position them as the educator and expert in their domain. Format: Theme name + 2-3 sentence description emphasizing educational value and expertise demonstration.
```

**Content Types**:
- **Concept Breakdown Posts**: Complex topic simplification into accessible insights
- **Framework Sharing Content**: Methodology and decision-making system education
- **Industry Analysis Teaching**: Market trend explanation and interpretation guidance
- **Skill Development Guides**: Capability building and professional growth education
- **Historical Context Education**: Industry evolution and pattern recognition teaching
- **Beginner-Friendly Explanations**: Entry-level education for complex domains
- **Advanced Technique Sharing**: Expert-level insight and methodology teaching
- **Resource Curation Posts**: Educational material compilation and recommendation
- **Live Teaching Opportunities**: Real-time education and Q&A engagement
- **Case Study Education**: Real-world example analysis and lesson extraction

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Teaching CEO approach for their expertise in ({EXPERTISE_DOMAIN}). Target educational content discovery and thought leadership positioning. Generate: 1) LinkedIn keyword integration around "how to {skill}", "{domain} explained", "{concept} framework", "learn {expertise area}", "{industry} education" - integrate naturally into educational content, 2) Content structure optimization: Clear learning objectives, step-by-step explanations, actionable takeaways, engagement through questions, 3) Educational engagement: Teaching community building, student question response, knowledge sharing network development, 4) Authority building: Subject matter expert positioning, educational thought leadership, teaching credential development, 5) Content amplification: Educational content sharing, teaching community engagement, expert network building. Goal is to establish authoritative teaching presence that attracts students and positions expertise.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Educational content engagement (saves, shares, meaningful learning discussions)
- Subject matter expert recognition (speaking invitations, media quotes, interviews)
- Teaching community development (followers seeking education and insight)
- Authority-driven opportunities (advisory roles, consultation requests, partnerships)

**Secondary Metrics**:
- Educational content referral and citation rates
- Conference and event teaching opportunity generation
- Media expert positioning and quote requests
- Professional development and training collaboration inquiries
- Thought leadership award and recognition achievement
"""}
    },
    {
        'name': 'LinkedIn Play 3: The Industry Contrarian',
        'markdown_content': {"data": """## **LinkedIn Play 3: The Industry Contrarian**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Industry Contrarian - Cut through noise by thoughtfully challenging industry orthodoxy.

**Strategic Theory**: Well-reasoned contrarian views generate engagement and position you as an independent thinker. This play works by identifying widely-held beliefs that data or experience contradicts, then articulating alternative viewpoints that make people reconsider assumptions. Success comes from thoughtful dissent that sparks valuable discussion and positions you as a fearless truth-teller.

**Expected Timeline**: Next 3 months - establish contrarian voice, spark initial industry debates, and position as thoughtful challenger.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Industry Contrarian approach. Focus on challenging conventional wisdom in their industry ({INDUSTRY_DOMAIN}). Consider widely-held beliefs they can challenge with data or experience. Themes should cover: 1) Sacred cow challenging and conventional wisdom questioning, 2) Data-driven myth busting and assumption challenging, 3) Alternative approach advocacy and different methodology promotion, 4) Industry critique and systemic problem identification, 5) Future prediction and contrarian trend analysis. Each theme should challenge orthodoxy while providing thoughtful alternative perspectives. Format: Theme name + 2-3 sentence description emphasizing contrarian positioning and thoughtful dissent.
```

**Content Types**:
- **Sacred Cow Challenge Posts**: Questioning widely-accepted industry beliefs
- **Data Contradiction Content**: Using evidence to challenge popular assumptions
- **Alternative Methodology Advocacy**: Promoting different approaches and solutions
- **Industry Critique Analysis**: Systematic problem identification and discussion
- **Contrarian Prediction Posts**: Alternative future scenarios and trend analysis
- **Myth Busting Documentation**: Debunking common industry misconceptions
- **Different Approach Justification**: Explaining alternative strategies and their benefits
- **Status Quo Questioning**: Challenging existing practices and standard procedures
- **Revolutionary Thinking**: Proposing fundamental changes to industry approaches
- **Iconoclastic Leadership**: Demonstrating courage to challenge establishment thinking

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Industry Contrarian approach in ({INDUSTRY_DOMAIN}). Target debate-generating and discussion-sparking content optimization. Generate: 1) LinkedIn keyword integration around "why {common belief} is wrong", "{industry} myths", "unpopular opinion {domain}", "contrarian view {topic}", "everyone says {belief} but" - integrate into challenging content, 2) Content structure optimization: Strong opinion hooks, evidence-based arguments, discussion-provoking questions, respectful dissent, 3) Engagement optimization: Debate facilitation, respectful disagreement management, thought-provoking discussion leadership, 4) Contrarian positioning: Independent thinker brand, fearless truth-teller reputation, thoughtful dissent leadership, 5) Content amplification: Debate participant engagement, contrarian community building, discussion leader network development. Goal is to build reputation as thoughtful industry challenger who sparks valuable discussions.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- High engagement rates (comments, debates, thoughtful discussion generation)
- Thought leader positioning and industry influence recognition
- Conference keynote and debate invitation opportunities
- Media interview and expert commentary requests for contrarian perspectives

**Secondary Metrics**:
- Industry response and acknowledgment of contrarian positions
- Debate and discussion quality (thoughtful engagement vs. simple agreement)
- Influence on industry conversation and agenda setting
- Partnership opportunities with other independent thinkers
- Authority building through fearless truth-telling reputation
"""}
    },
    {
        'name': 'LinkedIn Play 4: The Customer Champion',
        'markdown_content': {"data": """## **LinkedIn Play 4: The Customer Champion**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Customer Champion - Make your customers the heroes of your LinkedIn narrative.

**Strategic Theory**: Customer-centric content builds trust and social proof simultaneously. By consistently highlighting customer success, challenges, and feedback, you demonstrate that customer outcomes drive your decisions. This play works because it shows rather than claims customer obsession while building a community of advocates. Success comes from authentic customer celebration that attracts prospects who want similar success.

**Expected Timeline**: Next 3 months - establish customer-centric voice, share initial success stories, and begin building customer advocacy foundation.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Customer Champion approach. Focus on customer success, feedback integration, and customer-centric decision making. Consider their customer base, success stories, and customer-driven insights. Themes should cover: 1) Customer success celebration and achievement highlighting, 2) Customer feedback integration and product evolution sharing, 3) Customer wisdom and insight amplification, 4) Customer challenge support and problem-solving collaboration, 5) Customer community building and advocacy development. Each theme should position customers as heroes while demonstrating customer obsession. Format: Theme name + 2-3 sentence description emphasizing customer-centric approach and success celebration.
```

**Content Types**:
- **Customer Success Spotlights**: Individual achievement celebration and story sharing
- **Customer Feedback Integration**: How user input shapes product and strategy decisions
- **Customer Wisdom Amplification**: Sharing insights and innovations from customer base
- **Customer Challenge Support**: Public problem-solving and support demonstration
- **Customer Community Celebration**: Highlighting user collaboration and mutual support
- **Customer Advisory Insights**: Wisdom from customer advisory board and feedback sessions
- **Customer Milestone Recognition**: Achievement celebration and success acknowledgment
- **Customer Learning Documentation**: Insights gained from customer interactions and feedback
- **Customer Advocacy Development**: Building champions and referral relationships
- **Customer-Driven Innovation**: Product development inspired by customer needs and requests

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Customer Champion approach. Target customer success, testimonial, and customer-centric content discovery. Generate: 1) LinkedIn keyword integration around "customer success", "{industry} results", "customer feedback", "user success story", "{product category} wins" - integrate into customer celebration content, 2) Content structure optimization: Customer achievement focus, success metric highlighting, gratitude expression, community building, 3) Customer engagement optimization: Customer response encouragement, success story amplification, customer voice elevation, 4) Social proof building: Customer advocacy development, testimonial content creation, success story network building, 5) Content amplification: Customer sharing encouragement, success story viral potential, customer champion network development. Goal is to build customer-centric brand that attracts prospects through authentic customer success demonstration.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Customer engagement with champion content (likes, shares, comments from customers)
- Customer advocacy development (referrals, testimonials, case study participation)
- Customer-driven lead generation (prospects attracted by customer success stories)
- Customer retention and satisfaction improvement through public celebration

**Secondary Metrics**:
- Customer-generated content and organic advocacy development
- Customer community building and peer-to-peer support network growth
- Customer success story conversion into sales materials and marketing assets
- Customer lifetime value improvement through championship and recognition
- Customer referral rate and word-of-mouth marketing acceleration
"""}
    },
    {
        'name': 'LinkedIn Play 5: The Connector CEO',
        'markdown_content': {"data": """## **LinkedIn Play 5: The Connector CEO**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Connector CEO - Build social capital by spotlighting others and facilitating valuable connections.

**Strategic Theory**: Giving first creates lasting reciprocity. This play builds your network by consistently highlighting others' achievements, making introductions, and sharing opportunities. It works through the principle that connectors become central nodes in valuable networks. Success comes from generous networking that makes you indispensable to your professional community.

**Expected Timeline**: Next 3 months - establish connector reputation, facilitate initial introductions, and build foundation for reciprocal networking.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Connector CEO approach. Focus on network building, relationship facilitation, and community connection. Consider their network, industry connections, and relationship-building opportunities. Themes should cover: 1) Achievement celebration and professional recognition of others, 2) Connection facilitation and introduction making between network members, 3) Opportunity sharing and community resource distribution, 4) Community building and network development activities, 5) Gratitude expression and relationship acknowledgment. Each theme should build social capital through generous networking and connection facilitation. Format: Theme name + 2-3 sentence description emphasizing generous networking and community building.
```

**Content Types**:
- **Achievement Celebration Posts**: Highlighting others' wins, promotions, and milestones
- **Virtual Introduction Posts**: Connecting people who should know each other
- **Opportunity Sharing Content**: Jobs, partnerships, speaking slots, and resources
- **Content Amplification Posts**: Resharing and adding value to others' insights
- **Community Highlight Posts**: Recognizing valuable community members and contributors
- **Resource Sharing Content**: Tools, articles, and insights that benefit your network
- **Event Connection Posts**: Facilitating meetups and networking opportunities
- **Gratitude and Acknowledgment**: Public thanks and recognition for help received
- **Collaboration Invitations**: Open calls for partnerships and joint initiatives
- **Network Wisdom Posts**: Sharing insights gained from your diverse network

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Connector CEO approach. Target networking, community building, and relationship content discovery. Generate: 1) LinkedIn keyword integration around "networking", "connections", "community building", "introductions", "{industry} leaders" - integrate naturally into networking content, 2) Content structure optimization: Clear value propositions, specific call-to-actions, community engagement focus, authentic relationship building, 3) Network engagement optimization: Connection facilitation, community response encouragement, relationship building network development, 4) Social capital building: Connector reputation development, network value demonstration, relationship facilitation leadership, 5) Content amplification: Network sharing encouragement, connection-driven viral potential, community builder network development. Goal is to build connector brand that attracts high-value network members and creates reciprocal relationships.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Network growth rate and quality (high-value connections vs. vanity metrics)
- Introduction success rate (connections made that result in meaningful relationships)
- Reciprocal support and collaboration opportunities generated
- Community leadership recognition and influence within networks

**Secondary Metrics**:
- Content amplification and sharing rates from network members
- Partnership and collaboration inquiries generated through networking
- Speaking and advisory opportunities resulting from network connections
- Business development pipeline generated through relationship building
- Community event organization success and attendance rates
"""}
    },
    {
        'name': 'LinkedIn Play 6: The Ecosystem Builder',
        'markdown_content': {"data": """## **LinkedIn Play 6: The Ecosystem Builder**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Ecosystem Builder - Showcase how collaboration and partnerships drive mutual success.

**Strategic Theory**: Platform success requires ecosystem health. This play demonstrates leadership by highlighting partner wins, collaborative innovations, and ecosystem growth. It works by showing that your success enables others' success, creating a virtuous cycle that attracts more ecosystem participants. Success comes from authentic ecosystem development that creates network effects through content.

**Expected Timeline**: Next 3 months - establish ecosystem focus, highlight initial partner wins, and demonstrate collaborative approach.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Ecosystem Builder approach. Focus on platform partnerships, collaborative success, and ecosystem development. Consider their partnership strategy, platform capabilities, and ecosystem opportunities. Themes should cover: 1) Partner success celebration and ecosystem wins, 2) Collaborative innovation and joint development stories, 3) Ecosystem metrics and growth sharing, 4) Partnership philosophy and ecosystem strategy, 5) Community event and ecosystem gathering insights. Each theme should demonstrate ecosystem leadership and collaborative success. Format: Theme name + 2-3 sentence description emphasizing ecosystem building and partnership success.
```

**Content Types**:
- **Partner Success Spotlights**: Celebrating ecosystem partners' achievements and growth
- **Collaboration Innovation Stories**: Documenting joint product development and innovation
- **Ecosystem Metrics Sharing**: Transparent reporting on platform growth and partner success
- **Partnership Philosophy Posts**: Explaining the "why" behind ecosystem strategy
- **Community Event Coverage**: Insights from partner summits and ecosystem gatherings
- **Co-Innovation Announcements**: Showcasing joint features and collaborative solutions
- **Ecosystem Resource Sharing**: Tools, guides, and resources for partner success
- **Platform Evolution Updates**: How partner feedback shapes product roadmap
- **Cross-Pollination Stories**: How partners learn from and help each other
- **Ecosystem Vision Content**: Future state of collaborative platform growth

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Ecosystem Builder approach. Target partnership, platform, and collaboration content discovery. Generate: 1) LinkedIn keyword integration around "partnerships", "ecosystem", "platform", "collaboration", "{industry} integrations" - integrate into partnership content, 2) Content structure optimization: Partnership value demonstration, collaboration success metrics, ecosystem growth evidence, mutual benefit emphasis, 3) Partnership engagement optimization: Partner response encouragement, ecosystem community building, collaborative content development, 4) Platform positioning: Ecosystem leader brand, collaboration facilitator reputation, platform authority development, 5) Content amplification: Partner sharing encouragement, ecosystem content network, collaborative success story spread. Goal is to build ecosystem leader brand that attracts partners and demonstrates platform value.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Partner application and onboarding rates (ecosystem attraction power)
- Platform transaction volume and partner-generated revenue
- Partner retention and satisfaction scores
- Cross-partner collaboration and referral rates

**Secondary Metrics**:
- Ecosystem event participation and community engagement
- Partner content co-creation and amplification rates
- Platform marketplace growth and activity levels
- Developer community size and engagement for technical platforms
- Media coverage of ecosystem strategy and partnership success
"""}
    },
    {
        'name': 'LinkedIn Play 7: The Data-Driven Executive',
        'markdown_content': {"data": """## **LinkedIn Play 7: The Data-Driven Executive**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Data-Driven Executive - Share exclusive data and insights that others can't access.

**Strategic Theory**: Data creates unique value in content marketing. This play leverages your access to proprietary data, customer insights, and industry intelligence to create thought leadership that competitors can't replicate. It works because original data analysis positions you as the definitive source of truth in your domain. Success comes from consistent sharing of unique insights that make your content essential reading for industry professionals.

**Expected Timeline**: Next 3 months - establish data authority, share initial proprietary insights, and build reputation for data-driven content.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Data-Driven Executive approach. Focus on proprietary data insights, industry analysis, and trend identification. Consider their data access, analytics capabilities, and unique intelligence sources. Themes should cover: 1) Industry benchmark sharing and performance analysis, 2) Trend identification and predictive insights from data, 3) Customer behavior analysis and pattern recognition, 4) Market intelligence and competitive landscape insights, 5) Myth-busting through data-driven evidence. Each theme should leverage unique data access to provide insights competitors cannot replicate. Format: Theme name + 2-3 sentence description emphasizing data authority and unique insights.
```

**Content Types**:
- **Industry Benchmark Reports**: Sharing aggregated performance data and industry standards
- **Trend Analysis Posts**: Identifying patterns and predicting future developments
- **Customer Behavior Insights**: Patterns and preferences derived from user data
- **Market Intelligence Updates**: Competitive landscape analysis and market shifts
- **Data-Driven Myth Busting**: Using evidence to challenge common assumptions
- **Performance Correlation Studies**: Identifying surprising connections in data
- **Predictive Analysis Content**: Future forecasting based on current data trends
- **Interactive Data Polls**: Engaging audience while collecting comparative intelligence
- **Annual State Reports**: Comprehensive yearly analysis of industry evolution
- **Real-Time Market Pulse**: Current events interpreted through data lens

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Data-Driven Executive approach. Target data, research, and industry intelligence queries. Generate: 1) LinkedIn keyword integration around "industry data", "benchmarks", "research insights", "market analysis", "{industry} trends" - integrate into analytical content, 2) Content structure optimization: Data visualization focus, methodology transparency, actionable insights extraction, credible source citation, 3) Authority building optimization: Primary source positioning, research credibility development, industry intelligence leadership, 4) Data presentation: Clear visualizations, executive summary focus, surprising insight highlighting, comparative analysis, 5) Content amplification: Research sharing encouragement, data citation network, industry intelligence community building. Goal is to establish data authority that makes content essential for industry decision-makers.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Content citation and reference rates by industry media and competitors
- Data download and sharing rates for reports and insights
- Media interview requests for industry commentary and expert opinion
- Research partnership and collaboration inquiries from industry organizations

**Secondary Metrics**:
- Analyst and researcher engagement with data content
- Conference speaking invitations for data presentations
- Industry publication guest writing opportunities
- Customer and prospect engagement with intelligence content
- Academic and think tank collaboration opportunities
"""}
    },
    {
        'name': 'LinkedIn Play 8: The Future-Back Leader',
        'markdown_content': {"data": """## **LinkedIn Play 8: The Future-Back Leader**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Future-Back Leader - Build authority by painting vivid pictures of where your industry is heading.

**Strategic Theory**: Visionary content attracts forward-thinking audiences and positions you as someone who sees around corners. This play works by demonstrating deep industry understanding through specific, reasoned predictions about the future. Rather than generic predictions, it provides detailed scenarios that help others prepare for and navigate change. Success comes from consistent future-focused insights that prove prescient over time.

**Expected Timeline**: Next 3 months - establish visionary voice, share initial future predictions, and begin building forward-thinking community.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Future-Back Leader approach. Focus on industry evolution, technology trends, and future scenario planning. Consider their domain expertise, market position, and unique insights into industry direction. Themes should cover: 1) Industry transformation scenarios and timeline predictions, 2) Technology evolution and adoption curve forecasting, 3) Workforce and skills transformation analysis, 4) Business model evolution and market structure changes, 5) Preparation strategies and adaptation guidance for future scenarios. Each theme should demonstrate visionary thinking while providing actionable preparation guidance. Format: Theme name + 2-3 sentence description emphasizing future vision and strategic foresight.
```

**Content Types**:
- **Future Scenario Planning**: Detailed 3-5 year industry evolution predictions
- **Technology Adoption Forecasts**: Timeline and impact analysis for emerging technologies
- **Workforce Transformation Analysis**: How roles and skills will evolve over time
- **Business Model Evolution**: Predictions about how industries will restructure
- **Obsolescence Predictions**: What current practices/technologies will disappear
- **Emergence Spotting**: Early identification of breakthrough trends and technologies
- **Timeline Roadmaps**: When key transformations will reach critical mass
- **Preparation Guides**: How individuals and organizations should adapt for future
- **Investment Thesis Sharing**: What trends justify long-term strategic bets
- **Contrarian Future Views**: Challenging popular predictions with alternative scenarios

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Future-Back Leader approach. Target future trends, predictions, and strategic planning content discovery. Generate: 1) LinkedIn keyword integration around "future of {industry}", "2030 predictions", "industry transformation", "technology trends", "strategic planning" - integrate into visionary content, 2) Content structure optimization: Specific timeline predictions, evidence-based reasoning, scenario planning frameworks, actionable preparation steps, 3) Visionary positioning: Future thought leader brand, strategic foresight reputation, transformation guide authority, 4) Prediction tracking: Timeline accountability, accuracy demonstration, scenario refinement over time, 5) Content amplification: Strategic planning community engagement, future-focused network building, visionary content sharing. Goal is to build futurist brand that attracts forward-thinking leaders and influences strategic decisions.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Prediction accuracy tracking and public accountability for forecasts
- Strategic advisor and board invitation opportunities based on future insights
- Media interview requests for trend analysis and future predictions
- Conference keynote invitations for visionary presentations

**Secondary Metrics**:
- Investment and strategic planning consultation requests
- Future-focused content engagement and discussion quality
- Industry analyst and thought leader engagement with predictions
- Academic and research institution collaboration on future studies
- Long-term brand association with accurate industry forecasting
"""}
    },
    {
        'name': 'LinkedIn Play 9: The Vulnerable Leader',
        'markdown_content': {"data": """## **LinkedIn Play 9: The Vulnerable Leader**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Vulnerable Leader - Build deep connections by sharing struggles, failures, and personal growth.

**Strategic Theory**: Strategic vulnerability accelerates trust and connection. This play involves sharing personal challenges, growth moments, and authentic struggles in ways that make you more relatable and human. It works because authenticity in leadership is rare and creates emotional bonds that transcend professional relationships. Success comes from genuine vulnerability that inspires others while building a loyal, engaged community.

**Expected Timeline**: Next 3 months - establish authentic voice, share initial vulnerable stories, and begin building trust-based connections.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Vulnerable Leader approach. Focus on authentic personal sharing, growth experiences, and leadership challenges. Consider their comfort level with vulnerability, personal experiences, and leadership journey. Themes should cover: 1) Leadership struggle sharing and growth documentation, 2) Personal challenge navigation and resilience building, 3) Failure analysis and learning extraction from setbacks, 4) Mental health and wellness journey in leadership roles, 5) Work-life integration reality and family impact sharing. Each theme should demonstrate authentic vulnerability while providing value to others facing similar challenges. Format: Theme name + 2-3 sentence description emphasizing authentic sharing and community connection.
```

**Content Types**:
- **Struggle Documentation**: Honest sharing of current leadership and personal challenges
- **Failure Analysis**: Deep dives into mistakes, setbacks, and lessons learned
- **Growth Journey Posts**: Personal development, therapy insights, and transformation stories
- **Mental Health Advocacy**: Depression, anxiety, burnout, and wellness journey sharing
- **Work-Life Reality**: Family impact, parenting lessons, and integration challenges
- **Imposter Syndrome Content**: Self-doubt, confidence issues, and overcoming inadequacy feelings
- **Health Journey Sharing**: Physical wellness, recovery stories, and lifestyle changes
- **Relationship Learning**: Marriage, friendship, and family insights applied to leadership
- **Financial Stress Stories**: Money worries, funding challenges, and financial growth
- **Identity Evolution**: How leadership changes you as a person and family member

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Vulnerable Leader approach. Target leadership development, mental health, and personal growth content discovery. Generate: 1) LinkedIn keyword integration around "leadership challenges", "founder struggles", "mental health", "work-life balance", "personal growth" - integrate sensitively into vulnerable content, 2) Content structure optimization: Story-based narratives, lesson extraction focus, community support encouragement, authentic voice maintenance, 3) Community building optimization: Safe space creation, vulnerable response encouragement, supportive network development, 4) Authentic positioning: Genuine leader brand, human-first reputation, vulnerability advocate authority, 5) Content amplification: Supportive community sharing, mental health advocacy network, authentic leadership community building. Goal is to build authentic leader brand that creates deep connections and supports others in similar struggles.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Deep engagement quality (meaningful comments, direct messages, personal sharing responses)
- Community support and reciprocal vulnerability from followers
- Mental health advocacy opportunities and speaking invitations
- Authentic leadership recognition and awards from community organizations

**Secondary Metrics**:
- Employee attraction and retention improvement through authentic culture demonstration
- Customer loyalty and brand affinity increases through human connection
- Media coverage of leadership authenticity and vulnerability advocacy
- Professional therapy and coaching referral opportunities
- Book, podcast, and speaking opportunities on authentic leadership topics
"""}
    },
    {
        'name': 'LinkedIn Play 10: The Grateful Leader',
        'markdown_content': {"data": """## **LinkedIn Play 10: The Grateful Leader**

### **1. Play Header & Overview**

**Play Name & One-Line Summary**: The Grateful Leader - Build loyalty and positive culture through consistent, specific gratitude.

**Strategic Theory**: Public gratitude creates positive cycles that compound over time. This play involves regularly acknowledging others' contributions with specificity and authenticity, creating a magnetic leadership brand that attracts talent, partners, and customers. It works by making people feel seen and valued, generating goodwill that translates into business value. Success comes from genuine appreciation that inspires reciprocal loyalty and positive brand association.

**Expected Timeline**: Next 3 months - establish grateful voice, implement regular appreciation practices, and begin seeing positive culture impacts.

### **2. Content System Structure**

**Content Themes**:

```
[LLM INSTRUCTION] Generate 3-5 core content themes for {FOUNDER_NAME} at {COMPANY_NAME} using The Grateful Leader approach. Focus on appreciation, recognition, and positive relationship building. Consider their team, community, customers, and support network. Themes should cover: 1) Team member recognition and specific contribution celebration, 2) Customer appreciation and success story sharing, 3) Mentor and advisor gratitude and wisdom sharing, 4) Community and industry support acknowledgment, 5) Personal and family support system recognition. Each theme should demonstrate genuine gratitude while building positive brand association and community loyalty. Format: Theme name + 2-3 sentence description emphasizing authentic appreciation and positive culture building.
```

**Content Types**:
- **Team Appreciation Posts**: Specific recognition of employee contributions and achievements
- **Customer Gratitude**: Thank you posts for customer loyalty, feedback, and success
- **Mentor Recognition**: Appreciation for advisors, investors, and guidance providers
- **Partner Acknowledgment**: Gratitude for collaboration, support, and joint successes
- **Community Thanks**: Recognition of industry supporters, early adopters, and advocates
- **Family Appreciation**: Personal gratitude for family support and understanding
- **Failure Support Recognition**: Thanks for those who helped during difficult times
- **Milestone Gratitude**: Appreciation posts during company achievements and celebrations
- **Random Acts Recognition**: Unexpected kindness and support acknowledgment
- **Historical Appreciation**: Looking back at early supporters and their continued impact

### **3. AI Optimization Approach**

```
[LLM INSTRUCTION] Create LinkedIn optimization strategy for {FOUNDER_NAME} implementing The Grateful Leader approach. Target leadership, culture, and positive workplace content discovery. Generate: 1) LinkedIn keyword integration around "gratitude", "team appreciation", "leadership culture", "employee recognition", "positive workplace" - integrate naturally into appreciation content, 2) Content structure optimization: Specific contribution highlighting, authentic emotion expression, positive culture demonstration, community building focus, 3) Culture building optimization: Positive workplace brand development, grateful leader reputation, appreciation culture advocacy, 4) Relationship strengthening: Employee loyalty building, customer appreciation demonstration, partner gratitude expression, 5) Content amplification: Appreciation network building, positive culture sharing, grateful leadership community development. Goal is to build grateful leader brand that attracts talent, retains customers, and creates positive business relationships.
```

### **4. Success Metrics & Measurement**

**Primary KPIs**:
- Employee retention and satisfaction improvement through public appreciation
- Customer loyalty and referral rates increase from gratitude-based relationship building
- Partner relationship strength and collaboration opportunities generated
- Positive brand association and culture reputation development

**Secondary Metrics**:
- Team member engagement with appreciation content (likes, shares, comments)
- Customer testimonial and advocacy development through gratitude cultivation
- Media coverage of positive leadership and culture practices
- Speaking opportunities on gratitude-based leadership and positive culture building
- Talent attraction improvement through positive culture demonstration and recognition
"""}
    }
]

# CUSTOMIZE THIS: Change the namespace if needed
NAMESPACE = "linkedin_playbook_sys"  # Fixed namespace for LinkedIn playbook system documents


async def upload_markdown_documents():
    """Upload all markdown documents defined in DOCUMENTS list as unversioned system documents"""
    
    # Authenticate and create client
    try:
        auth_client = await AuthenticatedClient().__aenter__()
        logger.info("Authenticated successfully.")
        client = CustomerDataTestClient(auth_client)
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise
    
    logger.info(f"Starting upload of {len(DOCUMENTS)} markdown documents as unversioned system documents...")
    logger.info(f"Namespace: {NAMESPACE}")
    
    # Upload each document as unversioned system document
    results = []
    for doc in DOCUMENTS:
        try:
            document_data = doc['markdown_content']
            
            # Create unversioned payload for system documents
            payload = CustomerDataUnversionedCreateUpdate(
                is_shared=True,
                data=document_data,
                is_system_entity=True
            )
            
            # Store as unversioned document
            result = await client.create_or_update_unversioned_document(
                namespace=NAMESPACE,
                docname=doc['name'],
                data=payload
            )
            
            if result:
                logger.info(f"Successfully uploaded: {doc['name']}")
                results.append(result)
            else:
                logger.error(f"Failed to upload: {doc['name']}")
                results.append(None)
                
        except Exception as e:
            logger.error(f"Error uploading {doc['name']}: {e}")
            results.append(None)
    
    # Report results
    successful = sum(1 for result in results if result is not None)
    logger.info(f"Upload completed: {successful}/{len(DOCUMENTS)} documents uploaded successfully")
    
    if successful < len(DOCUMENTS):
        logger.warning(f"{len(DOCUMENTS) - successful} documents failed to upload")
    else:
        logger.info("All documents uploaded successfully as unversioned system documents! ✅")
    
    return results


if __name__ == "__main__":
    print("=== Markdown Document Uploader for LinkedIn Playbook System ===")
    print(f"Ready to upload {len(DOCUMENTS)} documents as unversioned system documents to namespace: {NAMESPACE}")
    print()
    
    asyncio.run(upload_markdown_documents())