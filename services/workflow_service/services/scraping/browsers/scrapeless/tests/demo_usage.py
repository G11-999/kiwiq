"""
Demo script for ScrapelessProfileManager with Async Context Manager

This script demonstrates practical usage of the comprehensive profile manager
including the new async context manager functionality, efficient cache handling,
and both manual and automatic resource management patterns.

Run this script to see the profile manager in action with different usage patterns.
"""

import asyncio
import threading
import time
from typing import List

from workflow_service.services.scraping.browsers.scrapeless.profiles import ScrapelessProfileManager, ProfileData


async def simulate_scraping_task(manager: ScrapelessProfileManager, task_id: int, duration: float) -> dict:
    """
    Simulate a scraping task that allocates a profile, uses it, and releases it.
    
    Args:
        manager: Profile manager instance
        task_id: Unique task identifier
        duration: How long to hold the profile (simulating scraping work)
        
    Returns:
        Dictionary with task results and profile usage info
    """
    print(f"🔍 Task {task_id}: Starting scraping simulation...")
    
    # Allocate profile
    profile = await manager.allocate_profile()
    if not profile:
        print(f"❌ Task {task_id}: Failed to allocate profile")
        return {"task_id": task_id, "success": False, "error": "No profile available"}
    
    print(f"✅ Task {task_id}: Allocated profile {profile.name} "
          f"(Penalty: {profile.penalty_score}, Active: {profile.actual_allocations}, "
          f"Total: {profile.total_allocations})")
    
    try:
        # Simulate scraping work
        print(f"⏳ Task {task_id}: Performing scraping work for {duration}s...")
        time.sleep(duration)
        
        # Simulate some work results
        results = {
            "task_id": task_id,
            "profile_used": profile.name,
            "profile_id": profile.profile_id,
            "penalty_score": profile.penalty_score,
            "actual_allocations": profile.actual_allocations,
            "total_allocations": profile.total_allocations, 
            "duration": duration,
            "success": True,
            "data_scraped": f"mock_data_from_task_{task_id}"
        }
        
        print(f"✅ Task {task_id}: Scraping completed successfully")
        return results
        
    finally:
        # Always release the profile
        if await manager.release_profile(profile.profile_id):
            print(f"🔄 Task {task_id}: Released profile {profile.name}")
        else:
            print(f"⚠️ Task {task_id}: Failed to release profile {profile.name}")


async def demonstrate_async_context_manager():
    """
    Demonstrate the new async context manager usage (RECOMMENDED).
    
    This shows the efficient approach where cache is saved only once at the end,
    reducing disk I/O latency during operations.
    """
    print("\n" + "="*60)
    print("🚀 ASYNC CONTEXT MANAGER DEMONSTRATION")
    print("="*60)
    print("Using 'async with' syntax for automatic resource management")
    print("Cache will be saved only once at the end (efficient)")
    
    # Create multiple concurrent tasks
    tasks = [
        (1, 1.5),  # Task 1: 1.5 seconds
        (2, 1.0),  # Task 2: 1 second
        (3, 2.0),  # Task 3: 2 seconds
        (4, 1.2),  # Task 4: 1.2 seconds
        (5, 1.8),  # Task 5: 1.8 seconds
    ]
    
    try:
        # Use async context manager (recommended approach)
        async with ScrapelessProfileManager(
            num_profiles=4,
            name_prefix="context-demo",
            cache_file="demo_context_profiles.json",
            save_cache_on_operations=False  # Efficient: save only on close
        ) as manager:
            
            print(f"\n📦 Profile manager opened automatically")
            
            # Show initial stats
            stats = await manager.get_stats()
            print(f"📊 Initial stats - Total profiles: {stats['total_profiles']}, "
                  f"Save on operations: {stats['configuration']['save_cache_on_operations']}")
            
            print(f"\n🎯 Starting {len(tasks)} concurrent scraping tasks...")
            print("💡 Notice: No cache saves during operations (efficient mode)")
            
            # Execute tasks concurrently
            async_tasks = [
                simulate_scraping_task(manager, task_id, duration)
                for task_id, duration in tasks
            ]
            
            # Run all tasks concurrently
            results = await asyncio.gather(*async_tasks, return_exceptions=True)
            
            # Filter out exceptions and log them
            successful_results = []
            for result in results:
                if isinstance(result, Exception):
                    print(f"❌ Task failed with error: {result}")
                else:
                    successful_results.append(result)
            
            # Show final statistics before closing
            stats = await manager.get_stats()
            print(f"\n📊 Pre-close statistics:")
            print(f"   Total active allocations: {stats['total_active_allocations']}")
            print(f"   Lifetime allocations: {stats.get('lifetime_statistics', {}).get('total_allocations', 0)}")
            print(f"   Lifetime releases: {stats.get('lifetime_statistics', {}).get('total_releases', 0)}")
            
            # Show task results
            print(f"\n📋 Task Results Summary:")
            print(f"   Successful tasks: {len(successful_results)}/{len(tasks)}")
            
        # Context manager automatically calls close() here and saves cache
        print(f"💾 Cache automatically saved on context manager exit")
        print(f"🔒 Profile manager automatically closed")
        
        return successful_results
        
    except Exception as e:
        print(f"❌ Context manager demo failed: {e}")
        return []


async def demonstrate_manual_management():
    """
    Demonstrate manual resource management with immediate cache saving.
    
    This shows the alternative approach where cache is saved on every operation
    for consistency-critical scenarios.
    """
    print("\n" + "="*60)
    print("🔧 MANUAL MANAGEMENT DEMONSTRATION")
    print("="*60)
    print("Using manual open/close with immediate cache saving")
    print("Cache will be saved on every allocate/release (consistent but slower)")
    
    # Create manager with immediate cache saving enabled
    manager = ScrapelessProfileManager(
        num_profiles=3,
        name_prefix="manual-demo", 
        cache_file="demo_manual_profiles.json",
        save_cache_on_operations=True  # Save cache on every operation
    )
    
    try:
        # Manual opening
        print(f"\n📦 Opening profile manager manually...")
        success = await manager.open()
        if not success:
            print("❌ Failed to open profile manager")
            return []
        
        stats = await manager.get_stats()
        print(f"📊 Manager stats - Opened: {stats['is_opened']}, "
              f"Save on operations: {stats['configuration']['save_cache_on_operations']}")
        
        # Perform operations with immediate cache saving
        print(f"\n🎯 Performing operations with immediate cache saving...")
        
        # Allocate profiles (each will save cache)
        allocated_profiles = []
        for i in range(1, 4):
            print(f"\n{i}️⃣ Allocating profile {i}:")
            profile = await manager.allocate_profile()  # Cache saved here
            if profile:
                allocated_profiles.append(profile)
                print(f"   💾 Cache saved immediately after allocation")
        
        # Show intermediate stats
        stats = await manager.get_stats()
        print(f"\n📊 Intermediate stats:")
        print(f"   Active allocations: {stats['total_active_allocations']}")
        for pid, details in stats.get('profile_details', {}).items():
            print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                  f"active={details['actual_allocations']}")
        
        # Release profiles (each will save cache)
        print(f"\n🔄 Releasing profiles with immediate cache saving...")
        for i, profile in enumerate(allocated_profiles, 1):
            print(f"\n{i}️⃣ Releasing profile {i}:")
            success = await manager.release_profile(profile.profile_id)  # Cache saved here
            if success:
                print(f"   💾 Cache saved immediately after release")
        
        # Show final stats
        stats = await manager.get_stats()
        print(f"\n📊 Final stats:")
        print(f"   Active allocations: {stats['total_active_allocations']}")
        print(f"   Total cache saves: {len(allocated_profiles) * 2} (allocate + release for each)")
        
        return [{"pattern": "manual", "profiles_used": len(allocated_profiles)}]
        
    except Exception as e:
        print(f"❌ Manual management demo failed: {e}")
        return []
    finally:
        # Manual closing
        print(f"\n🔒 Closing profile manager manually...")
        await manager.close()  # Final cache save
        print(f"💾 Final cache save on close")


async def demonstrate_concurrent_usage():
    """
    Legacy demonstration method updated to use context manager.
    
    This maintains backward compatibility while showcasing the new approach.
    """
    print("\n" + "="*60)
    print("🚀 CONCURRENT USAGE DEMONSTRATION (Updated)")
    print("="*60)
    
    # Create multiple concurrent tasks
    tasks = [
        (1, 2.0),  # Task 1: 2 seconds
        (2, 1.5),  # Task 2: 1.5 seconds
        (3, 3.0),  # Task 3: 3 seconds
        (4, 1.0),  # Task 4: 1 second
        (5, 2.5),  # Task 5: 2.5 seconds
        (6, 1.8),  # Task 6: 1.8 seconds
        (7, 2.2),  # Task 7: 2.2 seconds
    ]
    
    try:
        # Use context manager for automatic resource management
        async with ScrapelessProfileManager(
            num_profiles=5, 
            name_prefix="concurrent-demo",
            cache_file="demo_concurrent_profiles.json",
        ) as manager:
            
            # Show initial stats
            print(f"\n📊 Initial Statistics:")
            stats = await manager.get_stats()
            print(f"   Total profiles: {stats['total_profiles']}")
            print(f"   Available profiles: {stats.get('available_profiles', stats['total_profiles'])}")
            print(f"   Active allocations: {stats['total_active_allocations']}")
            print(f"   Penalty system: allocation_penalty={stats.get('penalty_system', {}).get('allocation_penalty', 2)}, "
                  f"release_recovery={stats.get('penalty_system', {}).get('release_recovery', 1)}")
            
            print(f"\n🎯 Starting {len(tasks)} concurrent scraping tasks...")
            
            # Execute tasks concurrently using asyncio
            async_tasks = [
                simulate_scraping_task(manager, task_id, duration)
                for task_id, duration in tasks
            ]
            
            # Run all tasks concurrently
            results = await asyncio.gather(*async_tasks, return_exceptions=True)
            
            # Filter out exceptions and log them
            filtered_results = []
            for result in results:
                if isinstance(result, Exception):
                    print(f"❌ Task failed with error: {result}")
                else:
                    filtered_results.append(result)
            
            # Show final statistics
            print(f"\n📊 Final Statistics:")
            stats = await manager.get_stats()
            print(f"   Total profiles: {stats['total_profiles']}")
            print(f"   Active allocations: {stats['total_active_allocations']}")
            print(f"   Penalty distribution: {stats.get('penalty_system', {}).get('penalty_distribution', {})}")
            
            # Show per-profile details
            print("   Profile Details:")
            for pid, details in stats.get('profile_details', {}).items():
                print(f"     {details['profile_name']}: penalty={details['penalty_score']}, "
                      f"active={details['actual_allocations']}, total={details['total_allocations']}")
            
            # Show task results
            print(f"\n📋 Task Results Summary:")
            successful_tasks = [r for r in filtered_results if r.get('success')]
            print(f"   Successful tasks: {len(successful_tasks)}/{len(tasks)}")
            
            return filtered_results
            
    except Exception as e:
        print(f"❌ Concurrent usage demo failed: {e}")
        if "API" in str(e) or "key" in str(e):
            print("💡 Troubleshooting steps:")
            print("   1. Check that SCRAPELESS_API_KEY is set in scraping_settings")
            print("   2. Verify your API key is valid and active")
            print("   3. Check your internet connection")
            print("   4. Ensure you have sufficient API credits")
        return []


async def demonstrate_profile_lifecycle():
    """
    Demonstrate complete profile lifecycle with context manager.
    """
    print("\n" + "="*60)
    print("🔄 PROFILE LIFECYCLE DEMONSTRATION (Updated)")
    print("="*60)
    
    try:
        async with ScrapelessProfileManager(
            num_profiles=3, 
            name_prefix="lifecycle-test",
            cache_file="demo_lifecycle_profiles.json",
        ) as manager:
            
            # Show initial setup
            print(f"\n1️⃣ Initial Setup:")
            profiles = await manager.get_profiles()
            print(f"   Created {len(profiles)} profiles")
            for profile in profiles:
                print(f"   - {profile.name} (ID: {profile.profile_id})")
            
            # Test profile operations
            print(f"\n2️⃣ Testing Profile Operations:")
            
            # Allocate and use profiles
            allocated = []
            for i in range(2):
                profile = await manager.allocate_profile()
                if profile:
                    allocated.append(profile)
                    print(f"   Allocated: {profile.name}")
            
            # Show stats during allocation
            stats = await manager.get_stats()
            print(f"   Active allocations: {stats.get('allocated_profiles', stats['total_active_allocations'])}")
            
            # Release profiles
            for profile in allocated:
                await manager.release_profile(profile.profile_id)
                print(f"   Released: {profile.name}")
            
            # Test reset functionality (if needed)
            print(f"\n3️⃣ Testing Reset Functionality:")
            print("   Note: Reset will be handled by context manager cleanup")
            
            return True
            
    except Exception as e:
        print(f"❌ Lifecycle demo failed: {e}")
        if "API" in str(e) or "key" in str(e):
            print("💡 Please check your API key configuration and try again")
        return False


async def cleanup_demo_profiles():
    """
    Clean up all demo profiles created during testing.
    
    Note: This function is now less critical since context managers
    can handle cleanup automatically, but is kept for explicit cleanup.
    """
    print(f"\n" + "="*60)
    print("🧹 CLEANUP DEMONSTRATION")
    print("="*60)
    print("Cleaning up any remaining demo profiles...")
    
    # Create temporary managers for cleanup
    cleanup_configs = [
        ("context-demo", "demo_context_profiles.json"),
        ("manual-demo", "demo_manual_profiles.json"), 
        ("concurrent-demo", "demo_concurrent_profiles.json"),
        ("lifecycle-test", "demo_lifecycle_profiles.json"),
    ]
    
    for i, (prefix, cache_file) in enumerate(cleanup_configs, 1):
        print(f"\n{i}️⃣ Cleaning up {prefix} profiles...")
        try:
            async with ScrapelessProfileManager(
                num_profiles=1,  # Minimal for cleanup
                name_prefix=prefix,
                cache_file=cache_file
            ) as manager:
                # Try to load any existing profiles and delete them
                profiles = await manager.get_profiles()
                if profiles:
                    success = await manager.delete_all_profiles()
                    if success:
                        print(f"   ✅ Deleted {len(profiles)} profiles")
                    else:
                        print(f"   ⚠️ Some profiles may not have been deleted")
                else:
                    print(f"   ℹ️ No profiles found to clean up")
                    
        except Exception as e:
            print(f"   ⚠️ Error during cleanup: {e}")


async def main():
    """
    Main demo function showcasing all new features.
    """
    print("🧪 SCRAPELESS PROFILE MANAGER DEMONSTRATION")
    print("=" * 70)
    print("🆕 NEW FEATURES DEMONSTRATED:")
    print("- Async context manager support ('async with' syntax)")
    print("- Efficient cache handling (save only on close by default)")
    print("- Optional immediate cache saving mode")
    print("- Delta tracking for accurate count updates")
    print("- Manual resource management when needed")
    print("- Cache files saved in ./data/ subdirectory")
    print("\n⚠️  Make sure you have SCRAPELESS_API_KEY configured!")
    
    # input("\nPress Enter to continue...")
    
    try:
        # Demonstrate new async context manager (recommended)
        print(f"\n🎯 RUNNING CONTEXT MANAGER DEMOS...")
        context_results = await demonstrate_async_context_manager()
        
        # Demonstrate manual management with immediate saving
        manual_results = await demonstrate_manual_management()
        
        # Run legacy demos updated with new patterns
        concurrent_results = await demonstrate_concurrent_usage()
        lifecycle_success = await demonstrate_profile_lifecycle()
        
        # Summary
        print(f"\n🎉 DEMONSTRATION SUMMARY:")
        print(f"   Context manager results: {len(context_results)} successful tasks")
        print(f"   Manual management results: {len(manual_results)} operations")
        print(f"   Concurrent usage results: {len(concurrent_results)} successful tasks")
        print(f"   Lifecycle demo: {'✅ Success' if lifecycle_success else '❌ Failed'}")
        
        print(f"\n✨ All demonstrations completed successfully!")
        print(f"   Recommended: Use 'async with' for automatic resource management")
        print(f"   Alternative: Use manual open/close for fine-grained control")
        
    except KeyboardInterrupt:
        print(f"\n⚠️ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
    finally:
        # Clean up any remaining profiles
        await cleanup_demo_profiles()
        print(f"\n🏁 Demo session ended")


if __name__ == "__main__":
    asyncio.run(main()) 