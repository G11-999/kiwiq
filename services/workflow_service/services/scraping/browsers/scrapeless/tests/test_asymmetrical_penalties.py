#!/usr/bin/env python3
"""
Test script for Asymmetrical Penalty System with Async Context Manager

This script demonstrates the new asymmetrical penalty allocation system
with async context manager support, where allocation adds +2 penalty and 
release subtracts -1 penalty, creating better load balancing and preventing 
profile overloading.

Updated to showcase both context manager and manual management patterns.
"""

import asyncio
from workflow_service.services.scraping.browsers.scrapeless.profiles import ScrapelessProfileManager, ProfileData


async def test_asymmetrical_penalties_context_manager():
    """
    Test the asymmetrical penalty system using async context manager (RECOMMENDED).
    
    Tests:
    - 2 profiles total
    - Allocation beyond pool size
    - Asymmetrical penalty scoring
    - Over-release safeguards
    - Cache saved only once at the end for efficiency
    """
    print("🧪 ASYMMETRICAL PENALTY SYSTEM TEST (Context Manager)")
    print("=" * 60)
    print("Testing scenario: 2 profiles, multiple allocations beyond pool size")
    print("Cache saving: Only once at the end (efficient)")
    print()
    
    try:
        # Use async context manager with efficient cache saving (default)
        async with ScrapelessProfileManager(
            num_profiles=2, 
            name_prefix="penalty-test-ctx",
            cache_file="penalty_test_context_profiles.json",
            save_cache_on_operations=False  # Efficient: save only on close
        ) as manager:
            
            print("📦 Profile manager opened automatically")
            stats = await manager.get_stats()
            print(f"📊 Config - Save on operations: {stats['configuration']['save_cache_on_operations']}")
            
            print("\n🎯 ALLOCATION PHASE - Beyond Pool Size")
            print("-" * 50)
            
            allocated_profiles = []
            
            # Allocate profile 1 (should get penalty +2, active +1)
            print("1️⃣ First allocation:")
            profile1 = await manager.allocate_profile()  # No cache save
            if profile1:
                allocated_profiles.append(profile1)
                print(f"   Expected: penalty=2, active=1, total=1")
                print("   💡 No cache save yet (efficient mode)")
            
            # Allocate profile 2 (should get penalty +2, active +1)  
            print("\n2️⃣ Second allocation:")
            profile2 = await manager.allocate_profile()  # No cache save
            if profile2:
                allocated_profiles.append(profile2)
                print(f"   Expected: penalty=2, active=1, total=1")
                print("   💡 No cache save yet (efficient mode)")
            
            # Allocate beyond pool size - should reuse profile with lowest penalty (both equal, so first one)
            print("\n3️⃣ Third allocation (beyond pool size):")
            profile3 = await manager.allocate_profile()  # No cache save
            if profile3:
                allocated_profiles.append(profile3)
                print(f"   Expected: penalty=4, active=2, total=2 (reusing {profile3.name})")
                print("   💡 No cache save yet (efficient mode)")
            
            # Fourth allocation - should use the other profile
            print("\n4️⃣ Fourth allocation:")
            profile4 = await manager.allocate_profile()  # No cache save
            if profile4:
                allocated_profiles.append(profile4)
                print(f"   Expected: penalty=4, active=2, total=2 (reusing {profile4.name})")
                print("   💡 No cache save yet (efficient mode)")
            
            # Show current statistics
            print(f"\n📊 Statistics After 4 Allocations:")
            stats = await manager.get_stats()
            penalty_dist = stats.get('penalty_system', {}).get('penalty_distribution', {})
            print(f"   Total active allocations: {stats['total_active_allocations']}")
            print(f"   Penalty distribution: {penalty_dist}")
            
            for pid, details in stats['profile_details'].items():
                print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                      f"active={details['actual_allocations']}, total={details['total_allocations']}")
            
            print(f"\n🔄 RELEASE PHASE - Asymmetrical Recovery")
            print("-" * 50)
            
            # Release profile 1 (should get penalty -1, active -1)
            print("1️⃣ First release:")
            if allocated_profiles:
                released_profile = allocated_profiles.pop(0)
                success = await manager.release_profile(released_profile.profile_id)  # No cache save
                print(f"   Released {released_profile.name}: {success}")
                print(f"   Expected: penalty=3, active=1")
                print("   💡 No cache save yet (efficient mode)")
            
            # Release profile 2
            print("\n2️⃣ Second release:")
            if allocated_profiles:
                released_profile = allocated_profiles.pop(0)
                success = await manager.release_profile(released_profile.profile_id)  # No cache save
                print(f"   Released {released_profile.name}: {success}")
                print(f"   Expected: penalty=3, active=1")
                print("   💡 No cache save yet (efficient mode)")
            
            # Release again - should continue working
            print("\n3️⃣ Third release:")
            if allocated_profiles:
                released_profile = allocated_profiles.pop(0)
                success = await manager.release_profile(released_profile.profile_id)  # No cache save
                print(f"   Released {released_profile.name}: {success}")
                print(f"   Expected: penalty=2, active=0 (fully released)")
                print("   💡 No cache save yet (efficient mode)")
            
            print("\n4️⃣ Fourth release:")
            if allocated_profiles:
                released_profile = allocated_profiles.pop(0)
                success = await manager.release_profile(released_profile.profile_id)  # No cache save
                print(f"   Released {released_profile.name}: {success}")
                print(f"   Expected: penalty=2, active=0 (fully released)")
                print("   💡 No cache save yet (efficient mode)")
            
            # Show final statistics
            print(f"\n📊 Final Statistics:")
            stats = await manager.get_stats()
            lifetime = stats.get('lifetime_statistics', {})
            print(f"   Lifetime allocations: {lifetime.get('total_allocations', 0)}")
            print(f"   Lifetime releases: {lifetime.get('total_releases', 0)}")
            print(f"   Over-release attempts: {lifetime.get('over_release_attempts', 0)}")
            
            for pid, details in stats['profile_details'].items():
                print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                      f"active={details['actual_allocations']}, total={details['total_allocations']}")
            
            print(f"\n🛡️  SAFEGUARD TEST - Over-Release Prevention")
            print("-" * 50)
            
            # Try to release more than allocated (should fail)
            print("Attempting to over-release (should be prevented):")
            profiles = await manager.get_profiles()
            test_profile = profiles[0] if profiles else None
            if test_profile:
                success = await manager.release_profile(test_profile.profile_id)  # No cache save
                print(f"   Over-release attempt: {success} (should be False)")
                
                stats = await manager.get_stats()
                over_releases = stats.get('lifetime_statistics', {}).get('over_release_attempts', 0)
                print(f"   Over-release attempts tracked: {over_releases}")
            
        # Context manager automatically saves cache here and closes
        print(f"💾 Cache automatically saved on context manager exit")
        print(f"🔒 Profile manager automatically closed")
        print(f"\n✅ ASYMMETRICAL PENALTY TEST COMPLETED (Context Manager)")
        
        return True
        
    except Exception as e:
        print(f"❌ Context manager test failed: {e}")
        if "API" in str(e) or "key" in str(e):
            print("💡 Check API configuration")
        return False


async def test_asymmetrical_penalties_manual():
    """
    Test the asymmetrical penalty system using manual management with immediate cache saving.
    
    This demonstrates the alternative approach for consistency-critical scenarios.
    """
    print("\n🧪 ASYMMETRICAL PENALTY SYSTEM TEST (Manual Management)")
    print("=" * 60)
    print("Testing scenario: 2 profiles with immediate cache saving")
    print("Cache saving: On every allocate/release (consistent but slower)")
    print()
    
    # Create manager with immediate cache saving enabled
    manager = ScrapelessProfileManager(
        num_profiles=2, 
        name_prefix="penalty-test-manual",
        cache_file="penalty_test_manual_profiles.json",
        save_cache_on_operations=True  # Save cache on every operation
    )
    
    try:
        # Manual opening
        print("📦 Opening profile manager manually...")
        success = await manager.open()
        if not success:
            print("❌ Failed to open profile manager")
            return False
        
        stats = await manager.get_stats()
        print(f"📊 Config - Save on operations: {stats['configuration']['save_cache_on_operations']}")
        
        print("\n🎯 ALLOCATION & RELEASE WITH IMMEDIATE CACHE SAVING")
        print("-" * 50)
        
        allocated_profiles = []
        
        # Allocate profiles with immediate cache saving
        for i in range(1, 4):  # 3 allocations for 2 profiles
            print(f"\n{i}️⃣ Allocation {i}:")
            profile = await manager.allocate_profile()  # Cache saved immediately
            if profile:
                allocated_profiles.append(profile)
                print(f"   Allocated: {profile.name} (penalty: {profile.penalty_score})")
                print(f"   💾 Cache saved immediately after allocation")
        
        # Show intermediate stats
        print(f"\n📊 Intermediate Statistics:")
        stats = await manager.get_stats()
        for pid, details in stats.get('profile_details', {}).items():
            print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                  f"active={details['actual_allocations']}")
        
        # Release profiles with immediate cache saving
        print(f"\n🔄 RELEASE WITH IMMEDIATE CACHE SAVING")
        print("-" * 30)
        
        for i, profile in enumerate(allocated_profiles, 1):
            print(f"\n{i}️⃣ Release {i}:")
            success = await manager.release_profile(profile.profile_id)  # Cache saved immediately
            if success:
                print(f"   Released: {profile.name}")
                print(f"   💾 Cache saved immediately after release")
        
        print(f"\n📊 Final Statistics:")
        stats = await manager.get_stats()
        lifetime = stats.get('lifetime_statistics', {})
        print(f"   Total cache saves: {lifetime.get('total_allocations', 0) + lifetime.get('total_releases', 0)} (immediate mode)")
        print(f"   Lifetime allocations: {lifetime.get('total_allocations', 0)}")
        print(f"   Lifetime releases: {lifetime.get('total_releases', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Manual management test failed: {e}")
        return False
    finally:
        # Manual closing
        print(f"\n🔒 Closing profile manager manually...")
        await manager.close()  # Final cache save
        print(f"💾 Final cache save on close")


async def demonstrate_load_balancing_context_manager():
    """
    Demonstrate how the asymmetrical penalty system provides better load balancing
    using the async context manager.
    """
    print(f"\n🎯 LOAD BALANCING DEMONSTRATION (Context Manager)")
    print("=" * 60)
    print("Showing how penalties prevent profile overloading")
    print("Using efficient cache saving (only once at the end)")
    
    try:
        async with ScrapelessProfileManager(
            num_profiles=3, 
            name_prefix="balance-test-ctx",
            cache_file="balance_test_context_profiles.json",
            save_cache_on_operations=False  # Efficient mode
        ) as manager:
            
            print(f"\n📈 Allocating 10 times with 3 profiles (showing load distribution):")
            allocations = []
            
            for i in range(1, 11):
                profile = await manager.allocate_profile()  # No cache save during loop
                if profile:
                    allocations.append(profile)
                    print(f"   Allocation {i}: {profile.name} (penalty: {profile.penalty_score}, "
                          f"active: {profile.actual_allocations})")
            
            # Show load distribution
            print(f"\n📊 Load Distribution After 10 Allocations:")
            stats = await manager.get_stats()
            for pid, details in stats['profile_details'].items():
                print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                      f"active={details['actual_allocations']}, total={details['total_allocations']}")
            
            # Release all and show recovery
            print(f"\n🔄 Releasing all allocations (showing penalty recovery):")
            for i, profile in enumerate(allocations, 1):
                success = await manager.release_profile(profile.profile_id)  # No cache save during loop
                print(f"   Release {i}: {profile.name} -> {success}")
            
            print(f"\n📊 Final Penalty Scores (after all releases):")
            stats = await manager.get_stats()
            for pid, details in stats['profile_details'].items():
                print(f"   {details['profile_name']}: penalty={details['penalty_score']}, "
                      f"active={details['actual_allocations']}")
        
        # Cache saved automatically here
        print(f"💾 Cache saved once at the end (efficient)")
        return True
        
    except Exception as e:
        print(f"❌ Load balancing test failed: {e}")
        return False


async def demonstrate_both_patterns_comparison():
    """
    Demonstrate both context manager and manual patterns side by side.
    """
    print(f"\n🔄 PATTERN COMPARISON DEMONSTRATION")
    print("=" * 60)
    print("Comparing context manager vs manual management patterns")
    
    # Test both patterns with same operations
    operations = [
        ("allocate", None),
        ("allocate", None), 
        ("release", 0),  # Release first allocated
        ("allocate", None),
        ("release", 0),  # Release first remaining
        ("release", 0),  # Release last
    ]
    
    results = {}
    
    # Test 1: Context Manager (Efficient)
    print(f"\n1️⃣ CONTEXT MANAGER PATTERN:")
    print("   Cache saved only once at the end")
    
    try:
        start_time = asyncio.get_event_loop().time()
        
        async with ScrapelessProfileManager(
            num_profiles=2,
            name_prefix="pattern-ctx",
            cache_file="pattern_comparison_ctx.json",
            save_cache_on_operations=False
        ) as manager:
            
            allocated = []
            
            for i, (op, param) in enumerate(operations, 1):
                if op == "allocate":
                    profile = await manager.allocate_profile()
                    if profile:
                        allocated.append(profile)
                        print(f"   Step {i}: Allocated {profile.name} (no cache save)")
                elif op == "release" and param is not None and param < len(allocated):
                    profile = allocated.pop(param)
                    success = await manager.release_profile(profile.profile_id)
                    print(f"   Step {i}: Released {profile.name} -> {success} (no cache save)")
        
        context_time = asyncio.get_event_loop().time() - start_time
        print(f"   💾 Cache saved once on exit")
        print(f"   ⏱️  Total time: {context_time:.3f}s")
        results["context_manager"] = context_time
        
    except Exception as e:
        print(f"   ❌ Context manager test failed: {e}")
        results["context_manager"] = None
    
    # Test 2: Manual Management (Immediate Saving)
    print(f"\n2️⃣ MANUAL MANAGEMENT PATTERN:")
    print("   Cache saved on every operation")
    
    manager = ScrapelessProfileManager(
        num_profiles=2,
        name_prefix="pattern-manual",
        cache_file="pattern_comparison_manual.json", 
        save_cache_on_operations=True
    )
    
    try:
        start_time = asyncio.get_event_loop().time()
        
        await manager.open()
        allocated = []
        
        for i, (op, param) in enumerate(operations, 1):
            if op == "allocate":
                profile = await manager.allocate_profile()  # Cache saved here
                if profile:
                    allocated.append(profile)
                    print(f"   Step {i}: Allocated {profile.name} (cache saved)")
            elif op == "release" and param is not None and param < len(allocated):
                profile = allocated.pop(param)
                success = await manager.release_profile(profile.profile_id)  # Cache saved here
                print(f"   Step {i}: Released {profile.name} -> {success} (cache saved)")
        
        await manager.close()  # Final cache save
        
        manual_time = asyncio.get_event_loop().time() - start_time
        print(f"   💾 Cache saved {len(operations) + 1} times (open + operations + close)")
        print(f"   ⏱️  Total time: {manual_time:.3f}s")
        results["manual_management"] = manual_time
        
    except Exception as e:
        print(f"   ❌ Manual management test failed: {e}")
        results["manual_management"] = None
    
    # Comparison
    print(f"\n📊 PATTERN COMPARISON RESULTS:")
    if results["context_manager"] and results["manual_management"]:
        print(f"   Context Manager: {results['context_manager']:.3f}s (1 cache save)")
        print(f"   Manual Management: {results['manual_management']:.3f}s ({len(operations) + 1} cache saves)")
        
        if results["context_manager"] < results["manual_management"]:
            speedup = results["manual_management"] / results["context_manager"]
            print(f"   🚀 Context manager is {speedup:.1f}x faster")
        
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"   ✅ Use context manager for batch operations (efficient)")
        print(f"   ⚙️  Use manual mode for consistency-critical scenarios")
    else:
        print(f"   ⚠️ Could not complete comparison due to errors")
    
    return results


async def cleanup_test_profiles():
    """
    Clean up all test profiles created during testing.
    """
    print(f"\n🧹 CLEANING UP TEST PROFILES")
    print("=" * 40)
    
    cleanup_configs = [
        ("penalty-test-ctx", "penalty_test_context_profiles.json"),
        ("penalty-test-manual", "penalty_test_manual_profiles.json"),
        ("balance-test-ctx", "balance_test_context_profiles.json"),
        ("pattern-ctx", "pattern_comparison_ctx.json"),
        ("pattern-manual", "pattern_comparison_manual.json"),
    ]
    
    for i, (prefix, cache_file) in enumerate(cleanup_configs, 1):
        print(f"{i}️⃣ Cleaning up {prefix} profiles...")
        try:
            async with ScrapelessProfileManager(
                num_profiles=1,  # Minimal for cleanup
                name_prefix=prefix,
                cache_file=cache_file
            ) as manager:
                profiles = await manager.get_profiles()
                if profiles:
                    success = await manager.delete_all_profiles()
                    if success:
                        print(f"   ✅ Deleted {len(profiles)} profiles")
                    else:
                        print(f"   ⚠️ Some profiles may remain")
                else:
                    print(f"   ℹ️ No profiles found")
        except Exception as e:
            print(f"   ⚠️ Error during cleanup: {e}")


async def main():
    """Run all asymmetrical penalty system tests with both patterns."""
    print("🧪 ASYMMETRICAL PENALTY SYSTEM COMPREHENSIVE TEST")
    print("=" * 70)
    print("🆕 UPDATED FEATURES DEMONSTRATED:")
    print("- Async context manager support ('async with' syntax)")
    print("- Efficient vs immediate cache saving patterns")
    print("- Delta tracking for accurate count updates")
    print("- Performance comparison between patterns")
    print("- Enhanced safeguards and error handling")
    print()
    
    try:
        # Test context manager pattern (recommended)
        print("🎯 TESTING CONTEXT MANAGER PATTERN...")
        ctx_success = await test_asymmetrical_penalties_context_manager()
        
        # Test manual management pattern
        print("\n🎯 TESTING MANUAL MANAGEMENT PATTERN...")
        manual_success = await test_asymmetrical_penalties_manual()
        
        # Test load balancing with context manager
        print("\n🎯 TESTING LOAD BALANCING...")
        balance_success = await demonstrate_load_balancing_context_manager()
        
        # Compare both patterns
        print("\n🎯 COMPARING PATTERNS...")
        comparison_results = await demonstrate_both_patterns_comparison()
        
        # Summary
        print(f"\n🎉 TEST SUMMARY:")
        print(f"   Context Manager Test: {'✅ PASSED' if ctx_success else '❌ FAILED'}")
        print(f"   Manual Management Test: {'✅ PASSED' if manual_success else '❌ FAILED'}")
        print(f"   Load Balancing Test: {'✅ PASSED' if balance_success else '❌ FAILED'}")
        print(f"   Pattern Comparison: {'✅ COMPLETED' if comparison_results else '❌ FAILED'}")
        
        all_passed = ctx_success and manual_success and balance_success
        
        if all_passed:
            print(f"\n🚀 ALL TESTS PASSED!")
            print("The asymmetrical penalty system is working correctly with both patterns.")
            print("✨ Recommended: Use async context manager for most scenarios")
        else:
            print(f"\n⚠️ Some tests failed. Check API configuration and try again.")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        return False
    finally:
        # Always clean up
        await cleanup_test_profiles()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1) 