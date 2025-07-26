import asyncio
import uuid
import json
import os
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

from workflow_service.services.scraping.browsers.scrapeless.scrapeless_browser import (
    ScrapelessBrowser, 
    ScrapelessBrowserPool,
    ScrapelessBrowserContextManager,
    cleanup_scrapeless_redis_pool
)
from workflow_service.services.scraping.browsers.actors.google_ai_mode_logged_out import GoogleAIModeBrowserActor
from workflow_service.services.scraping.browsers.actors.perplexity_logged_out import PerplexityBrowserActor
from workflow_service.services.scraping.browsers.actors.openai_logged_out import OpenAIBrowserActor
from workflow_service.services.scraping.settings import scraping_settings
from workflow_service.services.scraping.browsers.config import MAX_CONCURRENT_SCRAPELESS_BROWSERS, ACQUISITION_TIMEOUT, BROWSER_TTL

from workflow_service.services.scraping.browsers.multi_provider_query_engine import MultiProviderQueryEngine, ProviderConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test and example usage
async def test_multi_provider_query_engine(cleanup_redis_pool: bool = True, test_queries: Optional[List[str]] = None):
    """Test the MultiProviderQueryEngine with sample queries."""
    
    if cleanup_redis_pool:
        # Force cleanup Redis pool before starting test to ensure clean state
        logger.info("🧹 Force cleaning up Redis pool before test...")
        try:
            await cleanup_scrapeless_redis_pool()
            logger.info("✅ Redis pool cleaned up successfully")
        except Exception as e:
            logger.error(f"Failed to cleanup Redis pool: {e}")
    
    # Define test queries
    test_queries = test_queries or [
        "What is the capital of France?",
        "How does photosynthesis work?", 
        "What are the benefits of renewable energy?"
    ]
    
    # Configure providers - you can enable/disable as needed
    providers_config = {
        "google": ProviderConfig(enabled=True, max_retries=2),
        "openai": ProviderConfig(enabled=True, max_retries=3), 
        "perplexity": ProviderConfig(enabled=True, max_retries=2)
    }
    
    # Create and run the query engine with cross-provider parallel processing
    enabled_providers_count = sum(1 for config in providers_config.values() if config.enabled)
    total_parallel_tasks = len(test_queries) * enabled_providers_count
    
    # Set browser pool size to demonstrate keep-alive optimization
    # - If browsers >= tasks: keep-alive will be DISABLED (saves resources)
    # - If browsers < tasks: keep-alive will be ENABLED (allows browser reuse)
    browser_pool_size = min(total_parallel_tasks, MAX_CONCURRENT_SCRAPELESS_BROWSERS)  # Sufficient browsers = no keep-alive needed

    print(f"🔄 Browser pool size: {browser_pool_size}")
    
    engine = MultiProviderQueryEngine(
        queries=test_queries,
        providers_config=providers_config,
        max_concurrent_browsers=browser_pool_size,
        browser_pool_config={
            "browser_ttl": BROWSER_TTL,  # 15 minutes
            "use_profiles": True,
            "acquisition_timeout": ACQUISITION_TIMEOUT,  # Longer timeout for parallel acquisition
            "persist_profile": False,
        }
    )
    
    try:
        # Process all queries
        results = await engine.process_all_queries()
        
        # Print summary
        summary = engine.get_summary_statistics(results)
        print("\n" + "="*80)
        print("🎉 QUERY PROCESSING SUMMARY")
        print("="*80)
        print(f"📋 Total queries: {summary['total_queries']}")
        print(f"⏱️  Total duration: {summary['total_duration']:.2f}s")
        print(f"✅ Overall success rate: {summary['overall']['overall_success_rate']:.1%}")
        print(f"📊 Total successful: {summary['overall']['total_successful_queries']}/{summary['overall']['total_possible_queries']}")
        
        print("\n📈 Per-Provider Results:")
        for provider, stats in summary["providers"].items():
            print(f"  {provider.upper()}: {stats['successful_queries']}/{test_queries.__len__()} "
                  f"({stats['success_rate']:.1%})")
        
        print(f"\n💾 Detailed results saved to: {engine.output_file}")
        
        # Demonstrate keep-alive optimization info
        print(f"\n⚙️ Keep-alive optimization:")
        if browser_pool_size >= total_parallel_tasks:
            print(f"   🔧 DISABLED - {browser_pool_size} browsers ≥ {total_parallel_tasks} tasks (saves resources)")
        else:
            print(f"   🔧 ENABLED - {browser_pool_size} browsers < {total_parallel_tasks} tasks (allows reuse)")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


# async def test_resource_cleanup():
#     """Test that Redis resources are properly cleaned up."""
#     logger.info("🧪 Testing resource cleanup...")
    
#     from redis_client.redis_client import AsyncRedisClient
#     from global_config.settings import global_settings
    
#     # Force cleanup before test
#     await cleanup_scrapeless_redis_pool()
    
#     redis_client = AsyncRedisClient(global_settings.REDIS_URL)
#     pool_key = scraping_settings.SCRAPELESS_BROWSERS_POOL_KEY
    
#     # Check initial state
#     initial_info = await redis_client.get_pool_info(pool_key)
#     logger.info(f"Initial pool state: {initial_info}")
    
#     # Create a pool and acquire a browser
#     pool = ScrapelessBrowserPool(
#         max_concurrent=2,
#         enable_keep_alive=False,
#         use_profiles=False
#     )
    
#     try:
#         # Test 1: Normal browser acquisition and release
#         logger.info("Test 1: Normal acquisition and release")
#         browser_data = await pool.acquire_browser()
#         assert browser_data is not None, "Failed to acquire browser"
        
#         mid_info = await redis_client.get_pool_info(pool_key)
#         logger.info(f"Pool state after acquisition: {mid_info}")
#         assert mid_info['current_usage'] == 1, f"Expected usage=1, got {mid_info['current_usage']}"
        
#         # Release browser
#         await pool.release_browser(browser_data)
        
#         after_release_info = await redis_client.get_pool_info(pool_key)
#         logger.info(f"Pool state after release: {after_release_info}")
#         assert after_release_info['current_usage'] == 0, f"Expected usage=0, got {after_release_info['current_usage']}"
        
#         # Test 2: Force close
#         logger.info("\nTest 2: Force close browser")
#         browser_data = await pool.acquire_browser()
#         assert browser_data is not None, "Failed to acquire browser"
        
#         await pool.force_close_browser(browser_data)
        
#         after_force_close_info = await redis_client.get_pool_info(pool_key)
#         logger.info(f"Pool state after force close: {after_force_close_info}")
#         assert after_force_close_info['current_usage'] == 0, f"Expected usage=0, got {after_force_close_info['current_usage']}"
        
#         # Test 3: Cleanup all browsers
#         logger.info("\nTest 3: Cleanup all browsers")
#         browser_data1 = await pool.acquire_browser()
#         browser_data2 = await pool.acquire_browser()
        
#         mid_info2 = await redis_client.get_pool_info(pool_key)
#         logger.info(f"Pool state with 2 browsers: {mid_info2}")
#         assert mid_info2['current_usage'] == 2, f"Expected usage=2, got {mid_info2['current_usage']}"
        
#         cleaned = await pool.cleanup_all_browsers()
#         logger.info(f"Cleaned up {cleaned} browsers")
        
#         final_info = await redis_client.get_pool_info(pool_key)
#         logger.info(f"Pool state after cleanup all: {final_info}")
#         assert final_info['current_usage'] == 0, f"Expected usage=0, got {final_info['current_usage']}"
        
#         logger.info("✅ All resource cleanup tests passed!")
        
#     except Exception as e:
#         logger.error(f"Test failed: {e}", exc_info=True)
#         # Cleanup on failure
#         await pool.cleanup_all_browsers()
#         raise
#     finally:
#         # Final cleanup
#         await cleanup_scrapeless_redis_pool()


if __name__ == "__main__":
    # Original single browser test  
    async def original_test():
        """Original test for comparison"""
        async with ScrapelessBrowser() as browser:
            print("\n\nLive URL:", await browser.get_live_url(), "\n\n")
            ai_mode_actor = GoogleAIModeBrowserActor(browser=browser.browser, context=browser.context, page=browser.page)
            # await ai_mode_actor.google_conversation("What is the capital of France?", "What is the capital of Germany?", "What is the capital of Italy?")
            await ai_mode_actor.single_query("What is the capital of France?")

    # Run the comprehensive multi-provider test
    async def main():
        print("🚀 Starting Multi-Provider Query Engine Test")
        print("=" * 80)
        
        # Option 1: Run resource cleanup test
        # await test_resource_cleanup()
        
        # Option 2: Run the comprehensive test
        queries = [
            "what is best AI sales intelligence platform for small teams under 20",
            "How does Momentum.io compare to traditional CRM systems like Salesforce?",
            "can truva ai automatically update hubspot with meeting notes",
            "What are the main differences between Goodmeetings and Gong for call analysis?",
            "does lace ai work for hvac plumbing roofing companies",
            "Which sales intelligence tool has the best Slack integration for real-time notifications?",
            "what does momentum io cost for 50 person sales team",
            "What specific metrics does Truva AI track for sales performance measurement?",
            "can goodmeetings provide real-time coaching during live sales calls",
            "How does Lace AI identify missed sales opportunities in home services businesses?",
            "what is roi timeline for ai sales intelligence platforms",
            "Which platform is better for B2B SaaS companies: Momentum.io or Truva AI?",
            "does goodmeetings integrate with microsoft teams and zoom",
            "How accurate is Lace AI's call classification for plumbing and roofing companies?",
            "what are key features in ai sales automation tools 2025",
            "Can Momentum.io automatically create deal rooms in Slack based on sales stage?",
            "how does truva ai free plan compare to outreach salesloft",
            "What kind of training is required to implement Goodmeetings for a sales team?",
            "how does lace ai handle customer privacy and call recording compliance",
            "Which AI sales platform provides the best sentiment analysis for customer interactions?",
            "can ai sales tools integrate with custom crm systems",
            "What is the typical conversion rate improvement seen with Lace AI implementation?",
            "how does momentum io ai copilot feature work during sales calls",
            "Are there any industry-specific limitations for using Truva AI in healthcare or finance?",
            "what makes goodmeetings different from basic call recording tools",
            "How long does it take to see measurable results after implementing AI sales intelligence?",
            "which platform is best for companies using salesforce ecosystem",
            "Can Lace AI work for home service franchises with multiple locations and call centers?",
            "what are security measures for ai sales platforms",
            "what are best multilingual support ai sales tools",

            # 
            "Can Lace AI work for home service franchises with multiple locations and call centers?",
            "what are security measures for ai sales platforms",
            "what are best multilingual support ai sales tools",
            "what are best multilingual support ai sales tools",
        ]

        queries = [
            "what is digital sales room software",
            "best digital sales room platforms 2025",
            "How does Recapped.io AI scoring compare to traditional deal qualification methods?",
            "digital sales room vs crm differences",
            "GetAccept video messaging roi statistics",
            "best mutual action plan tools b2b sales",
            "How to implement digital sales rooms for enterprise accounts with multiple stakeholders?",
            "cpq integration digital sales rooms",
            "DealHub pricing enterprise vs mid market",
            "sales room buyer engagement tracking features",
            "What security certifications does Bigtincan offer for healthcare sales teams?",
            "free digital sales room alternatives",
            "Dock.us customer onboarding automation capabilities",
            "best ai powered sales intelligence platforms",
            "How does Flowla automation reduce manual follow-up tasks for sales reps?",
            "digital sales room mobile optimization",
            "salesforce integration sales room platforms",
            "GetAccept vs docusign sales team features",
            "How do digital sales rooms improve deal velocity in complex B2B transactions?",
            "best white label client portal solutions",
            "Recapped.io competitor comparison features pricing",
            "sales enablement vs digital sales rooms",
            "What analytics does Allego provide for video-based sales training effectiveness?",
            "multi language support sales room platforms",
            "hubspot native integration digital sales rooms",
            "How does DealHub handle complex pricing configurations for enterprise software sales?",
            "best sales room template libraries",
            "FuseBase ai workspace features review",
            "digital sales room soc2 compliance options",
            "How to measure buyer engagement scores in digital sales environments?",
            "sales room content management systems",
            "automated proposal generation tools sales",
            "Bigtincan vs seismic content management",
            "How does Dock.us facilitate handoffs between sales and customer success teams?",
            "contract lifecycle management sales rooms",
            "best video messaging platforms sales teams",
            "digital sales room implementation timeline",
            "What integration options does GetAccept offer with popular CRM systems?",
            "sales room analytics dashboard customization",
            "recurring revenue management digital platforms",
            "How do mutual action plans in Flowla improve sales accountability?",
            "best deal desk software features",
            "Aligned platform b2b collaboration tools",
            "digital sales room api documentation",
            "How does Recapped.io integrate with existing sales tech stacks?",
            "sales room personalization capabilities",
            "best cpq software small businesses",
            "channel partner collaboration digital tools",
            "What training resources does Allego provide for new sales team onboarding?",
            "sales room mobile app features",
            "quote to cash automation platforms",
            "How does Bigtincan AI improve sales content recommendations?",
            "digital sales room migration strategies",
            "best sales intelligence tracking tools",
            "FuseBase client portal customization options",
            "How to reduce sales cycle length using digital sales room analytics?",
            "automated follow up sequences sales",
            "subscription billing integration sales platforms",
            "What e-signature capabilities does DealHub offer for contract execution?",
            "digital sales room competitive analysis",
            "best sales forecasting accuracy tools",
            "How does GetAccept track prospect interaction with sales materials?",
            "sales room workflow automation features",
            "multi stakeholder deal management platforms",
            "What reporting capabilities does Dock.us provide for sales managers?",
            "digital sales room roi calculation methods",
            "best sales training video platforms",
            "How does Flowla handle complex approval workflows for enterprise deals?",
            "sales room document version control",
            "account based selling digital tools",
            "What AI features does Recapped.io offer for deal risk assessment?",
            "digital sales room enterprise security features",
            "best sales proposal design tools",
            "How does Bigtincan support global sales teams with multi-language content?",
            "sales room integration marketing automation",
            "automated contract approval workflows",
            "What customer success metrics does Allego track for sales training programs?",
            "digital sales room compliance healthcare",
            "best sales room financial services",
            "How does DealHub subscription management compare to dedicated billing platforms?",
            "sales room buyer journey tracking",
            "email integration digital sales platforms",
            "What collaboration features does FuseBase offer for client project management?",
            "digital sales room data migration",
            "best sales content analytics platforms",
            "How does GetAccept pricing compare to competitors for mid-market companies?",
            "sales room user permission management",
            "automated sales admin task reduction",
            "What machine learning capabilities does Dock.us use for buyer insights?",
            "digital sales room saas implementation",
            "best deal coaching analytics tools",
            "How does Flowla AutoPilot compare to other sales automation platforms?",
            "sales room custom branding options",
            "revenue intelligence platform comparison",
            "What integration capabilities does Recapped.io offer with existing workflows?",
            "digital sales room team collaboration",
            "best sales room manufacturing industry",
            "How does Bigtincan GenieAI assist with real-time sales coaching?",
            "sales room prospect communication tracking",
            "automated mutual action plan creation",
            "What onboarding support does Allego provide for enterprise implementations?",
            "digital sales room pricing model comparison",
            "best client portal project tracking",
            "How does DealHub no-code CPQ compare to traditional configuration tools?",
            "sales room calendar integration features",
            "buyer engagement scoring algorithms",
            "What video analytics does GetAccept provide for sales performance optimization?",
            "digital sales room scalability enterprise",
            "best sales room renewal management",
            "How does FuseBase AI streamline content creation for client communications?"
            ]
        await test_multi_provider_query_engine(cleanup_redis_pool=False, test_queries=queries)
        
        # Option 3: Uncomment to run original test
        # await original_test()
    
    asyncio.run(main())


