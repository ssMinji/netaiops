#!/usr/bin/env python3
"""
Memory Validation Test Script
Tests both short-term and long-term memory functionality with agent runtime

NOTE: This is a GUIDED MANUAL TEST due to authentication requirements.
Each test requires you to run the command and verify the results manually.
"""
import subprocess
import sys
import time

def print_command_and_wait(test_name, cmd, expected_result):
    """Print test command and wait for user to run it"""
    print(f"\n🧪 {test_name}")
    print("=" * 60)
    print(f"📋 Copy and run this command in another terminal:")
    print(f"   {cmd}")
    print(f"\n✅ Expected Result:")
    print(f"   {expected_result}")
    
    # Wait for user to run the command
    print(f"\n💡 Instructions:")
    print(f"   1. Copy the command above")
    print(f"   2. Run it in another terminal window")
    print(f"   3. Observe the results")
    print(f"   4. Come back here and press ENTER when done")
    
    input("\n⏸️  Press ENTER after you've run the command and observed the results...")
    
    # Now ask for validation
    print("\n" + "-" * 40)
    response = input("Did the test pass as expected? (y/n/skip): ").lower().strip()
    if response == 'n':
        print("❌ Test marked as FAILED")
        return False
    elif response == 'skip':
        print("⏸️  Test skipped")
        return None
    else:
        print("✅ Test marked as PASSED")
        return True

def validate_memory():
    """Run guided memory validation tests"""
    print("🧠 MEMORY VALIDATION TEST SUITE - GUIDED MANUAL TESTS")
    print("=" * 60)
    print("💡 Note: Each test requires authentication. Run commands in sequence.")
    print("🔐 You'll authenticate once per command, but can reuse the same session.")
    
    results = {}
    
    # Test 1: Long-term Memory - Store User Permissions
    results['permission_storage'] = print_command_and_wait(
        "TEST 1: LONG-TERM MEMORY - STORE PERMISSIONS",
        "python3 test/test_agent.py troubleshooting_agent_runtime --prompt \"I belong to security-group-ops@example.com and nacl-ops@example.com. Please store this information for future sessions.\"",
        "Agent should acknowledge storing your permissions and mention security-group-ops and nacl-ops groups"
    )
    
    # Test 2: Long-term Memory - Recall Permissions (Different Session)
    results['permission_recall'] = print_command_and_wait(
        "TEST 2: LONG-TERM MEMORY - PERMISSION RECALL (NEW SESSION)",
        "python3 test/test_agent.py troubleshooting_agent_runtime --prompt \"Fix connectivity between client.examplecorp.com and server.examplecorp.com on port 443 using security group rules.\"",
        "Agent should NOT ask 'Do you belong to security-group-ops@example.com?' - it should remember from Test 1"
    )
    
    # Test 3: Short-term Memory - Interactive Session Tracking
    results['session_tracking'] = print_command_and_wait(
        "TEST 3: SHORT-TERM MEMORY - SESSION TRACKING",
        "python3 test/test_agent.py troubleshooting_agent_runtime --interactive",
        """In the interactive session, run these commands in sequence:
        1. 'Check connectivity between app-frontend.examplecorp.com and app-backend.examplecorp.com using TCP on port 80'
        2. 'What tools did I use in this session?'
        3. 'Summarize the operations performed in this session'
        4. 'quit'
        
        Expected: Agent should track and list tools used (dns-resolve, connectivity-check)"""
    )
    
    # Test 4: Long-term Memory - Conversation History
    results['conversation_history'] = print_command_and_wait(
        "TEST 4: LONG-TERM MEMORY - CONVERSATION HISTORY",
        "python3 test/test_agent.py troubleshooting_agent_runtime --prompt \"What was the last connectivity issue we worked on together?\"",
        "Agent should reference previous connectivity tests from earlier sessions (client.examplecorp.com and server.examplecorp.com)"
    )
    
    # Test 5: Permission Validation - NACL Operations
    results['nacl_permissions'] = print_command_and_wait(
        "TEST 5: PERMISSION VALIDATION - NACL OPERATIONS",
        "python3 test/test_agent.py troubleshooting_agent_runtime --prompt \"I need to modify NACL rules to allow traffic between subnets.\"",
        "Agent should use stored NACL permissions and NOT ask 'Do you belong to nacl-ops@example.com?'"
    )
    
    # Final Results Summary
    print("\n" + "=" * 60)
    print("🎯 MEMORY VALIDATION RESULTS SUMMARY")
    print("=" * 60)
    
    print("\n📊 Long-term Memory Tests:")
    print(f"   🔒 Permission Storage:     {format_result(results.get('permission_storage'))}")
    print(f"   🧠 Permission Recall:      {format_result(results.get('permission_recall'))}")
    print(f"   💭 Conversation History:   {format_result(results.get('conversation_history'))}")
    print(f"   🛡️  NACL Permissions:      {format_result(results.get('nacl_permissions'))}")
    
    print("\n📈 Short-term Memory Tests:")
    print(f"   📊 Session Tracking:       {format_result(results.get('session_tracking'))}")
    
    # Count results
    passed = sum(1 for r in results.values() if r is True)
    total = len([r for r in results.values() if r is not None])
    
    print(f"\n🏆 Overall Results: {passed}/{total} tests passed")
    
    if passed == total and total > 0:
        print("🎉 ALL MEMORY TESTS PASSED! AgentCore Memory is working correctly!")
    elif passed > 0:
        print("⚠️  Some memory features working, check failed tests above")
    else:
        print("❌ Memory functionality needs investigation")
    
    print(f"\n💡 Memory Implementation Status:")
    if results.get('permission_storage') and results.get('permission_recall'):
        print("✅ Long-term permission storage: WORKING")
    else:
        print("❌ Long-term permission storage: ISSUES")
        
    if results.get('session_tracking'):
        print("✅ Short-term session tracking: WORKING")
    else:
        print("❌ Short-term session tracking: ISSUES")

def format_result(result):
    """Format test result for display"""
    if result is True:
        return "✅ PASS"
    elif result is False:
        return "❌ FAIL"
    else:
        return "⏸️  SKIP"

if __name__ == "__main__":
    validate_memory()
