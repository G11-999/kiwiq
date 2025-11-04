from typing import List
from kiwi_client.test_run_workflow_client import (
    SetupDocInfo,
    CleanupDocInfo
)
from kiwi_client.workflows.active.sandbox_identifiers import test_sandbox_company_name as company_name
from kiwi_client.workflows.active.document_models.customer_docs import (
    BLOG_COMPANY_DOCNAME,
    BLOG_COMPANY_NAMESPACE_TEMPLATE,
    BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE
)

setup_docs: List[SetupDocInfo] = [
        # Company Goals Document
        {
            'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name),
            'docname': BLOG_COMPANY_DOCNAME,
            'initial_data': {
                "name": "KiwiQ",
                "website_url": "https://www.kiwiq.ai",
                "value_proposition": "AI-powered content generation platform specifically designed for B2B SaaS companies. Our platform leverages GPT-5 and proprietary algorithms to create high-quality blog posts, whitepapers, and marketing content that resonates with technical B2B audiences.",
                "company_goals": [
                    "Become the leading AI-powered content creation platform for B2B SaaS companies",
                    "Achieve 10,000 active users by end of 2025", 
                    "Expand into enterprise market with custom solutions",
                    "Build strategic partnerships with major marketing agencies",
                    "Establish thought leadership in AI content generation space"
                ],
                "target_metrics": {
                    "user_growth": "50% MoM",
                    "revenue_target": "10M ARR by 2025",
                    "customer_satisfaction": "NPS > 50"
                }
            },
            'is_shared': False,
            'is_versioned': False,
            'is_system_entity': False,
        },
        # Sample Internal Company Documents (multiple docs under uploaded files namespace)
#         {
#             'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
#             'docname': "kiwiq_product_overview_doc_1",
#             'initial_data': {"doc_data": """KiwiQ is an advanced AI-powered content generation platform designed specifically for B2B SaaS companies. Our platform leverages GPT-5 and proprietary algorithms to create high-quality blog posts, whitepapers, and marketing content.       
#                         Key Features:
#                         - AI content generation with industry-specific training
#                         - SEO optimization built into every piece of content
#                         - Content calendar management and scheduling
#                         - Multi-channel publishing (blog, LinkedIn, Twitter)
#                         - Advanced analytics dashboard with content performance metrics
#                         - Team collaboration tools for content review and approval
#                         - Integration with major CMS platforms (WordPress, HubSpot, etc.)

#                         Our unique value proposition is the industry-specific training that ensures content resonates with technical B2B audiences. Unlike general-purpose AI writers, ContentAI understands the nuances of SaaS marketing, technical concepts, and enterprise buyer journeys.

#                         Technology Stack:
#                         - Frontend: React with TypeScript
#                         - Backend: Python FastAPI
#                         - AI Models: Fine-tuned GPT-5 with proprietary training data
#                         - Infrastructure: AWS with auto-scaling capabilities
#                         - Database: PostgreSQL for structured data, Redis for caching
#                         """},
#             'is_shared': False,
#             'is_versioned': False,
#             'is_system_entity': False,
#         },
#         {
#             'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
#             'docname': "kiwiq_product_overview_doc_2",
#             'initial_data': {"doc_data": """
#             # KiwiQ User Guide

# ## Welcome to KiwiQ

# This comprehensive guide will help you get started with KiwiQ and master all its features to transform your content operations.

# ## Table of Contents

# 1. [Getting Started](#getting-started)
# 2. [Dashboard Overview](#dashboard-overview)
# 3. [Content Diagnostics](#content-diagnostics)
# 4. [Content Creation Studio](#content-creation-studio)
# 5. [Content Optimization](#content-optimization)
# 6. [Analytics & Reporting](#analytics-reporting)
# 7. [Integrations Setup](#integrations-setup)
# 8. [Best Practices](#best-practices)
# 9. [Troubleshooting](#troubleshooting)

# ---

# ## Getting Started

# ### Account Setup

# #### Step 1: Registration
# 1. Visit www.kiwiq.ai/signup
# 2. Enter your business email
# 3. Verify your email address
# 4. Complete your profile information

# #### Step 2: Company Profile
# 1. Navigate to **Settings > Company Profile**
# 2. Enter your company information:
#   - Company name and website
#   - Industry and target audience
#   - Content goals and objectives
#   - Brand voice and guidelines

# #### Step 3: Team Setup
# 1. Go to **Settings > Team Management**
# 2. Click **Invite Team Members**
# 3. Assign roles:
#   - **Admin**: Full platform access
#   - **Editor**: Content creation and editing
#   - **Viewer**: Read-only access

# ### Initial Configuration

# #### Connect Your Website
# 1. Navigate to **Integrations > CMS**
# 2. Select your CMS platform
# 3. Follow the authentication flow
# 4. Verify connection with test sync

# #### Setup Analytics
# 1. Go to **Integrations > Analytics**
# 2. Connect Google Analytics 4
# 3. Connect Google Search Console
# 4. Configure data sync frequency

# ---

# ## Dashboard Overview

# ### Main Dashboard Components

# #### Performance Metrics Panel
# - **Content Published**: Total articles this month
# - **Organic Traffic**: Current vs. previous period
# - **AI Visibility Score**: LLM citation tracking
# - **SEO Health**: Overall technical score

# #### Quick Actions
# - **New Content Brief**: Start content creation
# - **Run Diagnostics**: Analyze existing content
# - **View Reports**: Access performance data
# - **Schedule Content**: Plan publishing calendar

# #### Activity Feed
# - Recent content updates
# - Team member activities
# - Integration status
# - System notifications

# ### Navigation Structure

# ```
# Main Menu
# ├── Dashboard
# ├── Content Studio
# │   ├── Create New
# │   ├── Content Calendar
# │   └── Drafts
# ├── Diagnostics
# │   ├── Run Analysis
# │   ├── Reports
# │   └── Recommendations
# ├── Analytics
# │   ├── Performance
# │   ├── SEO Metrics
# │   └── AI Visibility
# ├── Integrations
# └── Settings
# ```

# ---

# ## Content Diagnostics

# ### Running Your First Diagnostic

# #### Step 1: Initiate Analysis
# 1. Click **Diagnostics > Run Analysis**
# 2. Select analysis type:
#   - **Quick Scan**: 5-minute overview
#   - **Deep Analysis**: Comprehensive audit
#   - **Competitor Analysis**: Benchmark comparison

# #### Step 2: Configure Parameters
# ```
# Analysis Settings:
# - Website URL: [your-domain.com]
# - Content Type: [Blog/Landing Pages/All]
# - Date Range: [Last 30/60/90 days]
# - Include Competitors: [Yes/No]
# ```

# #### Step 3: Review Results

# ##### Content Health Report
# - **Technical SEO Issues**
#   - Crawlability problems
#   - Missing meta descriptions
#   - Broken links
#   - Page speed issues

# - **Content Quality Metrics**
#   - Readability scores
#   - Content depth analysis
#   - Keyword optimization
#   - Semantic structure

# - **AI Visibility Assessment**
#   - LLM-friendly formatting
#   - Schema markup status
#   - Featured snippet potential
#   - Voice search optimization

# ### Understanding Diagnostic Scores

# #### SEO Health Score (0-100)
# - **90-100**: Excellent - Minor optimizations only
# - **70-89**: Good - Some improvements needed
# - **50-69**: Fair - Significant opportunities
# - **Below 50**: Poor - Critical issues to address

# #### AI Visibility Score (0-100)
# - Measures how well content performs in AI search
# - Tracks citations in ChatGPT, Claude, etc.
# - Analyzes structured data implementation
# - Evaluates content comprehensiveness

# ---

# ## Content Creation Studio

# ### Creating Your First Content Brief

# #### Step 1: Choose Creation Method

# ##### Method A: AI-Suggested Topics
# 1. Click **Create New > AI Suggestions**
# 2. System analyzes your:
#   - Current content gaps
#   - Competitor content
#   - Search trends
#   - User intent data
# 3. Select from suggested topics

# ##### Method B: Manual Input
# 1. Click **Create New > Manual Brief**
# 2. Enter your topic or idea
# 3. Add context and requirements

# #### Step 2: Research & Validation

# The platform automatically performs:
# - **Google Research**: Top-ranking content analysis
# - **Reddit Research**: User discussions and pain points
# - **Competitor Analysis**: Content gap identification
# - **Keyword Research**: Search volume and difficulty

# #### Step 3: Brief Generation

# ##### AI-Generated Brief Components
# ```
# Content Brief Structure:
# 1. Title and Meta Description
# 2. Target Keywords (Primary & Secondary)
# 3. Search Intent Analysis
# 4. Content Outline
#   - Introduction hooks
#   - Main sections
#   - Subheadings
#   - Conclusion CTA
# 5. Word Count Recommendation
# 6. Internal Linking Opportunities
# 7. Visual Content Suggestions
# 8. SEO Optimization Checklist
# ```

# ### Content Calendar Management

# #### Planning Your Content
# 1. Navigate to **Content Studio > Calendar**
# 2. View monthly/weekly/daily views
# 3. Drag and drop to reschedule
# 4. Color coding by status:
#   - 🔵 Planned
#   - 🟡 In Progress
#   - 🟢 Published
#   - 🔴 Needs Review

# #### Batch Operations
# - Select multiple content pieces
# - Apply bulk actions:
#   - Change status
#   - Assign team members
#   - Update categories
#   - Schedule publishing

# ### Writing with AI Assistance

# #### Step 1: Open Editor
# 1. Click on any content brief
# 2. Select **Start Writing**
# 3. Choose writing mode:
#   - **Full AI Generation**: Complete article
#   - **Section by Section**: Guided writing
#   - **Outline Only**: Manual writing

# #### Step 2: AI Writing Features

# ##### Smart Suggestions
# - Real-time SEO recommendations
# - Readability improvements
# - Fact-checking alerts
# - Citation suggestions

# ##### Writing Tools
# - **Rewrite**: Improve any paragraph
# - **Expand**: Add more detail
# - **Summarize**: Create concise versions
# - **Tone Adjust**: Match brand voice

# #### Step 3: Optimization Check
# Before publishing, the system checks:
# - ✅ Keyword density
# - ✅ Meta descriptions
# - ✅ Image alt text
# - ✅ Internal links
# - ✅ Readability score
# - ✅ Grammar and spelling

# ---

# ## Content Optimization

# ### Optimizing Existing Content

# #### Identify Optimization Opportunities
# 1. Go to **Diagnostics > Reports**
# 2. Filter by **Needs Optimization**
# 3. Sort by potential impact

# #### Optimization Workflow

# ##### Step 1: Select Content
# - Choose article to optimize
# - Review current performance metrics
# - Identify specific issues

# ##### Step 2: Apply Optimizations
# Available optimization types:
# - **Content Refresh**: Update statistics and information
# - **SEO Enhancement**: Improve keyword targeting
# - **Structure Improvement**: Better headings and formatting
# - **Length Expansion**: Add comprehensive coverage
# - **Visual Enhancement**: Add images and videos

# ##### Step 3: A/B Testing
# 1. Create variant versions
# 2. Split traffic between versions
# 3. Monitor performance metrics
# 4. Implement winning version

# ### Content Repurposing

# #### Repurpose Workflows
# Transform existing content into:
# - **Social Media Posts**: LinkedIn, Twitter threads
# - **Email Newsletters**: Subscriber content
# - **Video Scripts**: YouTube content
# - **Infographics**: Visual summaries
# - **Podcasts Scripts**: Audio content

# #### Automated Repurposing
# 1. Select source content
# 2. Choose target format
# 3. AI generates adapted version
# 4. Review and edit
# 5. Schedule distribution

# ---

# ## Analytics & Reporting

# ### Performance Dashboard

# #### Key Metrics Tracked
# - **Traffic Metrics**
#   - Page views
#   - Unique visitors
#   - Session duration
#   - Bounce rate

# - **Engagement Metrics**
#   - Time on page
#   - Scroll depth
#   - Social shares
#   - Comments

# - **Conversion Metrics**
#   - Lead generation
#   - Email signups
#   - Demo requests
#   - Sales attribution

# ### Custom Reports

# #### Creating Custom Reports
# 1. Navigate to **Analytics > Custom Reports**
# 2. Select metrics to include
# 3. Choose visualization type:
#   - Line graphs
#   - Bar charts
#   - Heat maps
#   - Tables
# 4. Set schedule for automated delivery

# #### Report Templates
# - **Executive Summary**: High-level KPIs
# - **Content Performance**: Detailed content metrics
# - **SEO Progress**: Search visibility tracking
# - **Competitor Comparison**: Benchmark analysis

# ### AI Visibility Tracking

# #### Monitor AI Performance
# - **ChatGPT Citations**: Track mentions
# - **Perplexity Appearances**: Answer inclusion
# - **Bing Chat References**: Content usage
# - **Google SGE**: Generative results

# #### Optimization Recommendations
# Based on AI tracking, receive:
# - Structure improvements
# - Content depth suggestions
# - FAQ additions
# - Schema markup updates

# ---

# ## Integrations Setup

# ### CMS Integration

# #### WordPress Setup
# 1. Install KiwiQ WordPress plugin
# 2. Enter API key from KiwiQ dashboard
# 3. Configure sync settings:
#   - Auto-publish
#   - Draft sync
#   - Category mapping
# 4. Test connection

# #### HubSpot Setup
# 1. Navigate to **Integrations > HubSpot**
# 2. Click **Connect HubSpot**
# 3. Authorize permissions
# 4. Map content types
# 5. Configure workflow triggers

# ### Analytics Integration

# #### Google Analytics 4
# 1. Go to **Integrations > GA4**
# 2. Sign in with Google account
# 3. Select property
# 4. Choose data streams
# 5. Configure metrics import

# #### Google Search Console
# 1. Navigate to **Integrations > GSC**
# 2. Verify domain ownership
# 3. Select properties
# 4. Configure data sync frequency

# ### Communication Tools

# #### Slack Integration
# 1. Click **Add to Slack**
# 2. Choose workspace
# 3. Select notification channel
# 4. Configure alerts:
#   - Content published
#   - Performance milestones
#   - Team mentions

# ---

# ## Best Practices

# ### Content Strategy Best Practices

# #### Topic Selection
# - Focus on user intent, not just keywords
# - Prioritize topics with business impact
# - Balance trending vs. evergreen content
# - Consider content clustering

# #### Content Quality
# - Aim for comprehensive coverage
# - Include original research or data
# - Add expert quotes and citations
# - Update content regularly

# #### SEO Optimization
# - Natural keyword integration
# - Optimize for featured snippets
# - Include related keywords
# - Build topical authority

# ### Workflow Best Practices

# #### Team Collaboration
# - Define clear roles and responsibilities
# - Use comments for feedback
# - Set realistic deadlines
# - Regular content reviews

# #### Content Calendar
# - Plan 1-2 months ahead
# - Mix content types
# - Align with business goals
# - Leave room for trending topics

# #### Performance Monitoring
# - Weekly performance reviews
# - Monthly strategy adjustments
# - Quarterly comprehensive audits
# - Annual strategy planning

# ---

# ## Troubleshooting

# ### Common Issues & Solutions

# #### Integration Issues

# **Problem**: CMS sync not working
# ```
# Solution:
# 1. Check API key validity
# 2. Verify permissions
# 3. Test connection
# 4. Contact support if persistent
# ```

# **Problem**: Analytics data missing
# ```
# Solution:
# 1. Confirm integration active
# 2. Check date range
# 3. Verify tracking code
# 4. Allow 24 hours for sync
# ```

# #### Content Creation Issues

# **Problem**: AI suggestions not relevant
# ```
# Solution:
# 1. Update company profile
# 2. Refine target audience
# 3. Add competitor URLs
# 4. Provide more context
# ```

# **Problem**: Brief generation stuck
# ```
# Solution:
# 1. Refresh browser
# 2. Clear cache
# 3. Try different topic
# 4. Check system status
# ```

# ### Getting Help

# #### Support Resources
# - **Help Center**: help.kiwiq.ai
# - **Video Tutorials**: kiwiq.ai/tutorials
# - **Community Forum**: community.kiwiq.ai
# - **Email Support**: support@kiwiq.ai

# #### Support Tiers
# - **Starter**: Email support (48h response)
# - **Professional**: Priority support (24h)
# - **Enterprise**: Dedicated success manager

# ### Keyboard Shortcuts

# #### Global Shortcuts
# - **Ctrl/Cmd + K**: Quick search
# - **Ctrl/Cmd + N**: New content
# - **Ctrl/Cmd + D**: Dashboard
# - **Ctrl/Cmd + ?**: Help menu

# #### Editor Shortcuts
# - **Ctrl/Cmd + S**: Save draft
# - **Ctrl/Cmd + Enter**: Publish
# - **Ctrl/Cmd + /**: AI suggestions
# - **Ctrl/Cmd + Z**: Undo

# ---

# ## Appendix

# ### Glossary of Terms

# - **AI Visibility**: How well content appears in AI-powered search
# - **Content Brief**: Detailed outline for content creation
# - **LLM**: Large Language Model (like ChatGPT)
# - **SGE**: Search Generative Experience (Google's AI search)
# - **SERP**: Search Engine Results Page
# - **CTR**: Click-Through Rate
# - **Core Web Vitals**: Google's page experience metrics

# ### System Requirements

# #### Browser Support
# - Chrome 90+
# - Firefox 88+
# - Safari 14+
# - Edge 90+

# #### Recommended Specifications
# - Screen resolution: 1366x768 minimum
# - Internet speed: 10 Mbps+
# - JavaScript enabled
# - Cookies enabled

# ---

# *Last Updated: January 2025*
# *Version: 2.0*
# *© KiwiQ - All Rights Reserved*
#                         """},
#             'is_shared': False,
#             'is_versioned': False,
#             'is_system_entity': False,
#         },
#         {
#             'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
#             'docname': "kiwiq_product_overview_doc_3",
#             'initial_data': {"doc_data": """
#             # KiwiQ Technical Architecture Documentation

# ## System Overview

# KiwiQ is built as a modern, scalable, microservices-based platform that leverages AI models, real-time data processing, and cloud-native technologies to deliver comprehensive content operations capabilities.

# ## Architecture Principles

# ### Core Design Principles
# - **Microservices Architecture**: Loosely coupled services for scalability
# - **Event-Driven Design**: Asynchronous processing for performance
# - **API-First Development**: RESTful and GraphQL APIs
# - **Cloud-Native**: Containerized, orchestrated deployment
# - **Security by Design**: Zero-trust architecture with encryption at rest and in transit

# ## High-Level Architecture

# ```
# ┌─────────────────────────────────────────────────────────────┐
# │                         Frontend Layer                       │
# │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
# │  │ React Web App│  │ Mobile PWA   │  │ Admin Portal │      │
# │  └──────────────┘  └──────────────┘  └──────────────┘      │
# └─────────────────────────────────────────────────────────────┘
#                               │
#                               ▼
# ┌─────────────────────────────────────────────────────────────┐
# │                        API Gateway                           │
# │               (Authentication, Rate Limiting)                │
# └─────────────────────────────────────────────────────────────┘
#                               │
#                               ▼
# ┌─────────────────────────────────────────────────────────────┐
# │                    Application Services                      │
# │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
# │  │Content Mgmt │  │ AI Engine   │  │ Analytics   │        │
# │  │   Service   │  │   Service   │  │   Service   │        │
# │  └─────────────┘  └─────────────┘  └─────────────┘        │
# │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
# │  │ Workflow    │  │ Integration │  │Notification │        │
# │  │   Engine    │  │    Hub      │  │   Service   │        │
# │  └─────────────┘  └─────────────┘  └─────────────┘        │
# └─────────────────────────────────────────────────────────────┘
#                               │
#                               ▼
# ┌─────────────────────────────────────────────────────────────┐
# │                      Data Layer                              │
# │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
# │  │ PostgreSQL  │  │   Redis     │  │ Elasticsearch│        │
# │  │  (Primary)  │  │   (Cache)   │  │   (Search)  │        │
# │  └─────────────┘  └─────────────┘  └─────────────┘        │
# └─────────────────────────────────────────────────────────────┘
# ```

# ## Component Architecture

# ### 1. Frontend Layer

# #### React Web Application
# - **Framework**: React 18 with TypeScript
# - **State Management**: Redux Toolkit with RTK Query
# - **UI Components**: Custom component library based on Tailwind CSS
# - **Build Tools**: Vite for development, optimized production builds
# - **Testing**: Jest, React Testing Library, Cypress for E2E

# #### Key Features
# - Server-side rendering for SEO
# - Progressive Web App capabilities
# - Real-time updates via WebSocket
# - Responsive design for all devices

# ### 2. API Gateway

# #### Technology Stack
# - **Framework**: Kong Gateway
# - **Authentication**: OAuth 2.0, JWT tokens
# - **Rate Limiting**: Token bucket algorithm
# - **Monitoring**: Prometheus metrics integration

# #### Endpoints Structure
# ```
# /api/v1/
# ├── /auth           - Authentication endpoints
# ├── /content        - Content management
# ├── /workflows      - Workflow operations
# ├── /analytics      - Performance metrics
# ├── /integrations   - Third-party connections
# └── /admin          - Administrative functions
# ```

# ### 3. Core Services

# #### Content Management Service
# - **Purpose**: Handle all content-related operations
# - **Technology**: Node.js with Express
# - **Database**: PostgreSQL for structured data
# - **Features**:
#   - CRUD operations for content
#   - Version control and history
#   - Content scheduling
#   - Multi-format support

# #### AI Engine Service
# - **Purpose**: Process AI-related requests
# - **Technology**: Python FastAPI
# - **ML Framework**: LangChain for LLM orchestration
# - **Models Integration**:
#   - OpenAI GPT-4 for content generation
#   - Claude for analysis and editing
#   - Perplexity for research
#   - Custom fine-tuned models

# #### Workflow Engine
# - **Purpose**: Orchestrate complex content workflows
# - **Technology**: Apache Airflow
# - **Features**:
#   - DAG-based workflow definition
#   - Parallel processing
#   - Error handling and retry logic
#   - Human-in-the-loop support

# #### Analytics Service
# - **Purpose**: Process and aggregate performance data
# - **Technology**: Node.js with streaming capabilities
# - **Data Processing**: Apache Spark for batch processing
# - **Real-time**: Apache Kafka for event streaming

# ### 4. Integration Layer

# #### Supported Integrations
# ```yaml
# CMS Platforms:
#   - WordPress (REST API)
#   - HubSpot (OAuth 2.0)
#   - Contentful (GraphQL)
#   - Ghost (Admin API)

# Analytics:
#   - Google Analytics 4 (Data API)
#   - Google Search Console (API)
#   - Adobe Analytics (API 2.0)

# SEO Tools:
#   - SEMrush (API v3)
#   - Ahrefs (API v2)
#   - Moz (API)

# Communication:
#   - Slack (Web API)
#   - Microsoft Teams (Graph API)
#   - Email (SMTP/SendGrid)
# ```

# ### 5. Data Architecture

# #### Primary Database (PostgreSQL)
# ```sql
# -- Core Tables Structure
# content_items (
#   id UUID PRIMARY KEY,
#   title VARCHAR(255),
#   slug VARCHAR(255) UNIQUE,
#   content JSONB,
#   status ENUM,
#   created_at TIMESTAMP,
#   updated_at TIMESTAMP,
#   metadata JSONB
# )

# workflows (
#   id UUID PRIMARY KEY,
#   name VARCHAR(255),
#   definition JSONB,
#   status ENUM,
#   created_by UUID,
#   execution_history JSONB[]
# )

# analytics_data (
#   id UUID PRIMARY KEY,
#   content_id UUID,
#   metric_type VARCHAR(50),
#   value NUMERIC,
#   timestamp TIMESTAMP,
#   source VARCHAR(50)
# )
# ```

# #### Cache Layer (Redis)
# - Session management
# - API response caching
# - Real-time analytics aggregation
# - Workflow state management

# #### Search Engine (Elasticsearch)
# - Full-text content search
# - Faceted search capabilities
# - Analytics aggregations
# - Log analysis

# ## Security Architecture

# ### Authentication & Authorization
# - **OAuth 2.0** for third-party integrations
# - **JWT tokens** for API authentication
# - **Role-Based Access Control (RBAC)**
# - **Multi-Factor Authentication (MFA)**

# ### Data Security
# - **Encryption at Rest**: AES-256 for database
# - **Encryption in Transit**: TLS 1.3
# - **Key Management**: AWS KMS or HashiCorp Vault
# - **Data Masking**: PII protection

# ### Compliance
# - **GDPR Compliant**: Data privacy controls
# - **SOC 2 Type II**: Security certification
# - **CCPA Ready**: California privacy law
# - **ISO 27001**: Information security

# ## Infrastructure

# ### Cloud Platform
# - **Primary**: AWS (us-east-1, eu-west-1)
# - **CDN**: CloudFlare for global distribution
# - **Container Orchestration**: Kubernetes (EKS)
# - **Service Mesh**: Istio for microservices communication

# ### Deployment Pipeline
# ```yaml
# CI/CD Pipeline:
#   1. Code Commit (GitHub)
#   2. Automated Tests (GitHub Actions)
#   3. Build Docker Images
#   4. Security Scanning (Snyk)
#   5. Deploy to Staging (ArgoCD)
#   6. Integration Tests
#   7. Deploy to Production (Blue-Green)
#   8. Health Checks
#   9. Monitoring Alerts
# ```

# ### Monitoring & Observability

# #### Metrics Collection
# - **Prometheus**: System and application metrics
# - **Grafana**: Visualization dashboards
# - **Custom Metrics**: Business KPIs

# #### Logging
# - **ELK Stack**: Elasticsearch, Logstash, Kibana
# - **Structured Logging**: JSON format
# - **Log Aggregation**: Centralized logging

# #### Tracing
# - **Jaeger**: Distributed tracing
# - **OpenTelemetry**: Instrumentation
# - **Performance Monitoring**: Real User Monitoring (RUM)

# ## Scalability Strategy

# ### Horizontal Scaling
# - Auto-scaling groups for services
# - Load balancing with health checks
# - Database read replicas
# - Caching at multiple levels

# ### Performance Optimization
# - **Response Time**: < 200ms p95
# - **Throughput**: 10,000 requests/second
# - **Availability**: 99.9% uptime SLA
# - **Data Processing**: Batch and stream processing

# ## API Design

# ### RESTful API Standards
# ```javascript
# // Example API Response Structure
# {
#   "status": "success",
#   "data": {
#     "id": "uuid",
#     "type": "content",
#     "attributes": {
#       // Resource attributes
#     },
#     "relationships": {
#       // Related resources
#     }
#   },
#   "meta": {
#     "timestamp": "2025-01-15T10:00:00Z",
#     "version": "1.0"
#   }
# }
# ```

# ### GraphQL Schema
# ```graphql
# type Content {
#   id: ID!
#   title: String!
#   slug: String!
#   body: String
#   status: ContentStatus!
#   author: User!
#   analytics: Analytics
#   createdAt: DateTime!
#   updatedAt: DateTime!
# }

# type Query {
#   content(id: ID!): Content
#   contents(filter: ContentFilter): [Content!]!
# }

# type Mutation {
#   createContent(input: ContentInput!): Content!
#   updateContent(id: ID!, input: ContentInput!): Content!
#   deleteContent(id: ID!): Boolean!
# }
# ```

# ## Development Environment

# ### Local Development Setup
# ```bash
# # Prerequisites
# - Docker Desktop
# - Node.js 18+
# - Python 3.11+
# - PostgreSQL 15
# - Redis 7

# # Environment Setup
# docker-compose up -d
# npm install
# npm run dev

# # Service URLs
# Frontend: http://localhost:3000
# API: http://localhost:8000
# Admin: http://localhost:3001
# ```

# ### Testing Strategy
# - **Unit Tests**: 80% code coverage minimum
# - **Integration Tests**: API endpoint testing
# - **E2E Tests**: Critical user journeys
# - **Performance Tests**: Load testing with K6
# - **Security Tests**: OWASP ZAP scanning

# ## Disaster Recovery

# ### Backup Strategy
# - **Database**: Daily automated backups, 30-day retention
# - **File Storage**: S3 versioning enabled
# - **Configuration**: Git-based config management
# - **Recovery Time Objective (RTO)**: 4 hours
# - **Recovery Point Objective (RPO)**: 1 hour

# ### Failover Procedures
# 1. Automatic health checks every 30 seconds
# 2. Automated failover to standby region
# 3. DNS update via Route53
# 4. Cache warming procedures
# 5. Notification to operations team

# ## Performance Benchmarks

# ### System Requirements
# - **CPU**: 8 cores minimum per service
# - **Memory**: 16GB RAM per service
# - **Storage**: SSD with 10,000 IOPS
# - **Network**: 10 Gbps internal connectivity

# ### Load Testing Results
# - **Concurrent Users**: 10,000
# - **Requests/Second**: 5,000
# - **Average Latency**: 150ms
# - **Error Rate**: < 0.1%

# ## Future Architecture Enhancements

# ### Planned Improvements
# 1. **Edge Computing**: Deploy services closer to users
# 2. **AI Model Optimization**: Custom model training pipeline
# 3. **Real-time Collaboration**: WebRTC integration
# 4. **Blockchain Integration**: Content verification
# 5. **Quantum-Ready Encryption**: Post-quantum cryptography

# ---

# *Last Updated: January 2025*
#     *Version: 2.0*"""},
#             'is_shared': False,
#             'is_versioned': False,
#             'is_system_entity': False,
#         },
#         {
#             'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
#             'docname': "kiwiq_target_audience_analysis_1",
#             'initial_data': {"doc_data": """# KiwiQ Product Overview

# ## Executive Summary

# KiwiQ is an AI-powered ContentOps platform designed to revolutionize how organizations create, optimize, and manage blog content. By leveraging advanced AI models and comprehensive data integration, KiwiQ helps marketing teams systematically improve content performance, identify high-impact opportunities, and automate content workflows.

# ## Problem We Solve

# Organizations face significant challenges in content management:
# - **Fragmented workflows** across analytics, SEO, CMS, and editorial tools
# - **Lack of unified strategy** for prioritizing content updates
# - **Difficulty identifying** high-impact content opportunities
# - **Manual processes** for SEO research and performance tracking
# - **Poor AI visibility** in emerging LLM-powered search engines

# ## Core Value Proposition

# KiwiQ delivers measurable results through:
# - **30% reduction** in content production time
# - **2x improvement** in SEO performance metrics
# - **Automated workflows** that eliminate manual research
# - **Data-driven insights** for content prioritization
# - **AI-optimized content** for better visibility in ChatGPT and other LLMs

# ## Key Features

# ### 1. Content Diagnostics Intelligence
# - **Comprehensive Content Audit**: Analyze existing blog content for performance gaps
# - **SEO Health Assessment**: Technical SEO analysis including crawlability, semantic structure, and Core Web Vitals
# - **AI Visibility Analysis**: Track and optimize content for LLM citations and bot traffic
# - **Competitor Benchmarking**: Compare content performance against industry competitors

# ### 2. Content Creation Studio
# - **AI-Powered Brief Generation**: Transform ideas into comprehensive content briefs
# - **Research Automation**: Automated Google and Reddit research for topic validation
# - **Topic Ideation Engine**: Generate high-impact content ideas based on data
# - **Content Calendar Management**: Plan and schedule content with AI recommendations

# ### 3. Content Optimization Workflows
# - **Content Update Prioritization**: Identify which content needs updates based on performance
# - **SEO Enhancement**: Automatic recommendations for improving search visibility
# - **Content Repurposing**: Transform existing content into new formats
# - **Performance Tracking**: Monitor content metrics across multiple channels

# ### 4. Data Integration Hub
# - **Google Analytics 4**: Session, engagement, and conversion tracking
# - **Google Search Console**: Keyword rankings, CTR, and search performance
# - **CMS Integration**: Direct connection to WordPress, HubSpot, and other platforms
# - **AI Bot Tracking**: Monitor ChatGPT-User and other AI crawler activity

# ## Target Users

# ### Primary Users
# - **Content Marketing Managers**: Leading content strategy and team execution
# - **SEO Specialists**: Optimizing content for search and AI visibility
# - **Marketing Directors**: Overseeing content ROI and performance

# ### Ideal Customer Profile
# - **Company Size**: 50-500 employees
# - **Industry**: B2B SaaS, Technology, Professional Services
# - **Content Volume**: Publishing 4+ blog posts per month
# - **Team Size**: 2-10 person marketing team

# ## Platform Architecture

# ### Technology Stack
# - **AI Models**: GPT-4, Claude, Perplexity for content generation
# - **Data Processing**: Real-time integration with analytics platforms
# - **Workflow Engine**: Automated pipeline for content operations
# - **User Interface**: Modern React-based dashboard

# ### Key Integrations
# - Google Analytics 4
# - Google Search Console
# - WordPress, HubSpot CMS
# - SEMrush, Ahrefs
# - Slack, Microsoft Teams

# ## Success Metrics

# ### Performance KPIs
# - **Content Production Speed**: 30% faster brief-to-publish cycle
# - **SEO Performance**: 2x improvement in organic traffic
# - **AI Visibility**: 50% increase in LLM citations
# - **Team Efficiency**: 40% reduction in manual research time

# ### Business Impact
# - **ROI**: 3x return on content investment within 6 months
# - **Lead Generation**: 45% increase in content-driven leads
# - **Brand Authority**: Improved thought leadership positioning

# ## Pricing Model

# ### Starter Plan - $499/month
# - Up to 10 content pieces per month
# - Basic SEO analysis
# - Standard integrations

# ### Professional Plan - $999/month
# - Up to 30 content pieces per month
# - Advanced AI features
# - Priority support
# - Custom integrations

# ### Enterprise Plan - Custom Pricing
# - Unlimited content
# - Dedicated success manager
# - Custom workflows
# - API access

# ## Competitive Advantages

# 1. **Unified Platform**: Single solution for entire content lifecycle
# 2. **AI-First Approach**: Built for the age of AI search and LLMs
# 3. **Data-Driven Insights**: Decisions based on real performance data
# 4. **Automation at Scale**: Reduce manual work by 70%
# 5. **Proven Methodology**: Based on successful content strategies

# ## Future Roadmap

# ### Q1 2025
# - LinkedIn content optimization
# - Advanced competitor analysis
# - Multi-language support

# ### Q2 2025
# - Video content optimization
# - Podcast content workflows
# - Enhanced AI personalization

# ### Q3 2025
# - Predictive content performance
# - Advanced attribution modeling
# - Enterprise API expansion

# ## Getting Started

# 1. **Discovery Call**: Understand your content challenges
# 2. **Platform Demo**: See KiwiQ in action
# 3. **Pilot Program**: 30-day trial with your content
# 4. **Onboarding**: Guided setup and integration
# 5. **Success Planning**: Develop content strategy with our team

# ## Contact Information

# **Website**: www.kiwiq.ai
# **Email**: hello@kiwiq.ai
# **Support**: support@kiwiq.ai
# **Sales**: sales@kiwiq.ai

# ---

# *KiwiQ - Transform Your Content Operations with AI*"""},
#             'is_shared': False,
#             'is_versioned': False,
#             'is_system_entity': False,
#         },
#         {
#             'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name),
#             'docname': "kiwiq_pricing_strategy_doc",
#             'initial_data': {"doc_data": """Tiered SaaS Pricing Model - Effective January 2025

# Starter Plan: 299 USD/month
# - 5 users
# - 20 AI-generated articles per month
# - Basic SEO optimization
# - Email support
# - Standard integrations

# Growth Plan: 799 USD/month  
# - 15 users
# - 60 AI-generated articles per month
# - Advanced SEO tools and keyword research
# - Priority support with 4-hour SLA
# - Custom integrations
# - Content calendar and workflow tools
# - Team collaboration features

# Enterprise Plan: 2499 USD/month
# - Unlimited users
# - Unlimited AI-generated articles
# - White-glove onboarding and training
# - Dedicated account manager
# - Custom AI model training on company data
# - API access for custom integrations
# - 99.9 percent uptime SLA
# - Quarterly business reviews

# Pricing Philosophy:
# - Positioned 30 percent below Jasper AI but with superior B2B features
# - Price based on value delivered (time saved times content quality)
# - Annual contracts receive 20 percent discount
# - Free 14-day trial with full features (no credit card required)

# Competitive Positioning:
# - Jasper AI: 50K USD/year enterprise - We're 60 percent less expensive with better B2B focus
# - Copy.ai: Consumer focused - We offer enterprise features they lack
# - Writesonic: Limited customization - We provide industry-specific models"""},
#             'is_shared': False,
#             'is_versioned': False,
#             'is_system_entity': False,
#         },
    ]

    # Add more example docs (kept smaller for brevity during tests)

cleanup_docs: List[CleanupDocInfo] = [
        {'namespace': BLOG_COMPANY_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': BLOG_COMPANY_DOCNAME, 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_1", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_2", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_product_overview_doc_3", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_target_audience_analysis_1", 'is_versioned': False, 'is_shared': False},
        {'namespace': BLOG_UPLOADED_FILES_NAMESPACE_TEMPLATE.format(item=company_name), 'docname': "kiwiq_pricing_strategy_doc", 'is_versioned': False, 'is_shared': False},
    ]