#!/usr/bin/env python3
"""
Simple test script for MultiProviderQueryEngine

This script demonstrates how to use the MultiProviderQueryEngine
to query multiple AI providers with configurable settings.
"""

import asyncio
import logging
from workflow_service.services.scraping.browsers.browser_test import MultiProviderQueryEngine, ProviderConfig

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def simple_test():
    """Simple test with a few queries and basic configuration."""
    
    print("🚀 Starting Simple MultiProviderQueryEngine Test")
    print("=" * 60)
    
    # Define test queries
    queries = [
        "What is artificial intelligence?",
        "How do solar panels work?"
    ]
    
    # Configure providers - enable only the ones you want to test
    providers_config = {
        "google": ProviderConfig(enabled=True, max_retries=1, timeout=120),
        "openai": ProviderConfig(enabled=False, max_retries=1, timeout=120),  # Disabled for faster testing
        "perplexity": ProviderConfig(enabled=False, max_retries=1, timeout=120)  # Disabled for faster testing
    }
    
    # Create query engine optimized for cross-provider parallel processing
    enabled_providers_count = sum(1 for config in providers_config.values() if config.enabled)
    total_parallel_tasks = len(queries) * enabled_providers_count
    
    print(f"📊 Task calculation: {len(queries)} queries × {enabled_providers_count} providers = {total_parallel_tasks} tasks")
    
    engine = MultiProviderQueryEngine(
        queries=queries,
        providers_config=providers_config,
        max_concurrent_browsers=total_parallel_tasks + 1,  # All queries across all providers + buffer
        browser_pool_config={
            "browser_ttl": 300,  # 5 minutes
            "use_profiles": True,
            "persist_profile": False,
            "acquisition_timeout": 30  # Reasonable timeout for parallel acquisition
        },
        output_file="simple_test_results.json"
    )
    
    try:
        # Process all queries
        print(f"📋 Processing {len(queries)} queries...")
        results = await engine.process_all_queries()
        
        # Print summary
        summary = engine.get_summary_statistics(results)
        
        print("\n" + "="*60)
        print("📊 TEST RESULTS SUMMARY")
        print("="*60)
        print(f"Total queries: {summary['total_queries']}")
        print(f"Duration: {summary['total_duration']:.1f}s")
        print(f"Overall success rate: {summary['overall']['overall_success_rate']:.1%}")
        
        print("\nPer-Provider Results:")
        for provider, stats in summary["providers"].items():
            status = "✅" if stats['success_rate'] > 0 else "❌"
            print(f"  {status} {provider.upper()}: {stats['successful_queries']}/{len(queries)} "
                  f"({stats['success_rate']:.1%})")
        
        print(f"\n💾 Full results saved to: {engine.output_file}")
        
        # Show sample response if available
        if results.get("results"):
            print("\n📄 Sample Response:")
            for provider_name, provider_results in results["results"].items():
                if provider_results and provider_results[0].get("success"):
                    response = provider_results[0]["response"]
                    if response and response.get("processed_data"):
                        sample_text = str(response["processed_data"])[:200]
                        print(f"  {provider_name}: {sample_text}...")
                    break
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        raise


async def advanced_test():
    """Advanced test with all providers and more queries."""
    
    print("🚀 Starting Advanced MultiProviderQueryEngine Test")
    print("=" * 60) 
    
    # More comprehensive queries
    queries = [
        "What is the capital of Japan?",
        "How does blockchain technology work?",
        "What are the main causes of climate change?"
    ]
    
    # Enable all providers with different retry strategies
    providers_config = {
        "google": ProviderConfig(enabled=True, max_retries=2, timeout=180),
        "openai": ProviderConfig(enabled=True, max_retries=2, timeout=180),
        "perplexity": ProviderConfig(enabled=True, max_retries=2, timeout=180)
    }
    
    # Optimized browser pool settings for cross-provider parallel processing
    enabled_providers_count = sum(1 for config in providers_config.values() if config.enabled)
    total_parallel_tasks = len(queries) * enabled_providers_count
    
    print(f"📊 Task calculation: {len(queries)} queries × {enabled_providers_count} providers = {total_parallel_tasks} tasks")
    
    # Option 1: Enough browsers (keep-alive DISABLED)
    browser_count_option1 = total_parallel_tasks + 2
    print(f"🔧 Option 1: {browser_count_option1} browsers ≥ {total_parallel_tasks} tasks → Keep-alive DISABLED")
    
    # Option 2: Fewer browsers (keep-alive ENABLED) - uncomment to test
    # browser_count_option2 = max(2, total_parallel_tasks // 2)
    # print(f"🔧 Option 2: {browser_count_option2} browsers < {total_parallel_tasks} tasks → Keep-alive ENABLED")
    
    engine = MultiProviderQueryEngine(
        queries=queries,
        providers_config=providers_config,
        max_concurrent_browsers=browser_count_option1,  # Use option 1 for this test
        browser_pool_config={
            "browser_ttl": 600,  # 10 minutes
            "use_profiles": True,
            "persist_profile": False,
            "acquisition_timeout": 45  # Longer timeout for parallel acquisition
        },
        output_file="advanced_test_results.json"
    )
    
    try:
        print(f"📋 Processing {len(queries)} queries across all providers...")
        results = await engine.process_all_queries()
        
        # Detailed summary
        summary = engine.get_summary_statistics(results)
        
        print("\n" + "="*60)
        print("📊 ADVANCED TEST RESULTS")
        print("="*60)
        print(f"Total queries: {summary['total_queries']}")
        print(f"Total providers: {len(summary['providers'])}")
        print(f"Duration: {summary['total_duration']:.1f}s")
        print(f"Overall success rate: {summary['overall']['overall_success_rate']:.1%}")
        print(f"Total successful: {summary['overall']['total_successful_queries']}/{summary['overall']['total_possible_queries']}")
        
        print(f"\n📈 Detailed Provider Results:")
        for provider, stats in summary["providers"].items():
            status_icon = "✅" if stats['success_rate'] == 1.0 else "⚠️" if stats['success_rate'] > 0 else "❌"
            print(f"  {status_icon} {provider.upper()}:")
            print(f"    • Success rate: {stats['success_rate']:.1%}")
            print(f"    • Successful: {stats['successful_queries']}")
            print(f"    • Failed: {stats['failed_queries']}")
        
        print(f"\n💾 Full results saved to: {engine.output_file}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Advanced test failed: {e}", exc_info=True)
        raise


async def main():
    """Main function to run tests."""
    
    print("🔬 MultiProviderQueryEngine Test Suite")
    print("=" * 80)
    
    # Ask user which test to run
    print("Available tests:")
    print("1. Simple test (Google only, 2 queries)")
    print("2. Advanced test (All providers, 3 queries)")
    print("3. Both tests")
    
    try:
        choice = input("\nSelect test (1/2/3) [default: 1]: ").strip() or "1"
        
        if choice == "1":
            await simple_test()
        elif choice == "2": 
            await advanced_test()
        elif choice == "3":
            print("\n🔄 Running simple test first...\n")
            await simple_test()
            print("\n" + "="*80)
            print("🔄 Now running advanced test...\n")
            await advanced_test()
        else:
            print("❌ Invalid choice. Running simple test...")
            await simple_test()
            
        print("\n🎉 All tests completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⏸️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main()) 