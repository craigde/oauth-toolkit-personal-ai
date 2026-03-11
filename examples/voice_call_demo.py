#!/usr/bin/env python3
"""
Voice Call Performance Demo
Demonstrates the low-latency access pattern critical for voice applications.

In voice applications, OAuth token access must be sub-10ms to feel natural.
This demo simulates a voice call scenario where multiple API calls are made
in quick succession, as would happen during a conversation.
"""

import time
import requests
import threading
from pathlib import Path
import sys

# Add providers to path
sys.path.append(str(Path(__file__).parent.parent))

from providers.google_oauth import GoogleOAuth


class VoiceCallSimulator:
    """Simulates a voice call session with multiple rapid API calls."""
    
    def __init__(self):
        self.google = GoogleOAuth()
        self.call_logs = []
        self.total_oauth_time = 0
        
    def simulate_voice_command(self, command_name: str, api_calls: list):
        """
        Simulate a single voice command that requires multiple API calls.
        
        Args:
            command_name: Description of the voice command
            api_calls: List of API endpoints to call
        """
        print(f"🎤 Voice Command: '{command_name}'")
        command_start = time.time()
        
        for i, api_call in enumerate(api_calls):
            # Measure OAuth token access time
            oauth_start = time.time()
            token = self.google.get_access_token()
            oauth_end = time.time()
            
            oauth_time = (oauth_end - oauth_start) * 1000  # ms
            self.total_oauth_time += oauth_time
            
            if not token:
                print(f"   ❌ API {i+1}: No token available")
                continue
                
            # Simulate API call
            try:
                headers = {'Authorization': f'Bearer {token}'}
                response = requests.get(api_call, headers=headers, timeout=5)
                
                api_time = time.time() - oauth_end
                status = "✅" if response.status_code < 400 else "❌"
                
                print(f"   {status} API {i+1}: OAuth {oauth_time:.1f}ms, API {api_time*1000:.1f}ms")
                
            except requests.RequestException as e:
                print(f"   ❌ API {i+1}: {str(e)[:50]}...")
        
        command_time = (time.time() - command_start) * 1000
        print(f"   🕐 Total: {command_time:.1f}ms\n")
        
        self.call_logs.append({
            'command': command_name,
            'total_time': command_time,
            'api_count': len(api_calls)
        })

    def run_voice_call_simulation(self):
        """Run a complete voice call simulation."""
        print("📞 Starting Voice Call Simulation")
        print("=" * 50)
        print("Simulating rapid-fire voice commands that require OAuth...")
        print()
        
        # Warm up the cache with one call
        print("🔥 Warming up OAuth cache...")
        warmup_token = self.google.get_access_token()
        if warmup_token:
            print("✅ Cache warmed\n")
        else:
            print("❌ Cache warmup failed - demo may be slow\n")
        
        # Simulate realistic voice commands
        commands = [
            {
                'name': 'Check my calendar for today',
                'apis': [
                    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
                    'https://www.googleapis.com/calendar/v3/users/me/calendarList'
                ]
            },
            {
                'name': 'Add event to calendar',
                'apis': [
                    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
                    'https://www.googleapis.com/calendar/v3/calendars/primary'
                ]
            },
            {
                'name': 'Check my emails',
                'apis': [
                    'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                    'https://gmail.googleapis.com/gmail/v1/users/me/profile'
                ]
            },
            {
                'name': 'Send an email',
                'apis': [
                    'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                    'https://gmail.googleapis.com/gmail/v1/users/me/profile'
                ]
            },
            {
                'name': 'Update calendar and notify via email',
                'apis': [
                    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
                    'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                    'https://www.googleapis.com/calendar/v3/calendars/primary'
                ]
            }
        ]
        
        # Execute commands with small delays (realistic conversation pace)
        for command in commands:
            self.simulate_voice_command(command['name'], command['apis'])
            time.sleep(0.5)  # Brief pause between commands
        
        self.print_performance_summary()

    def print_performance_summary(self):
        """Print detailed performance analysis."""
        print("📊 Voice Call Performance Analysis")
        print("=" * 50)
        
        if not self.call_logs:
            print("❌ No commands executed")
            return
        
        total_commands = len(self.call_logs)
        total_apis = sum(log['api_count'] for log in self.call_logs)
        avg_oauth_time = self.total_oauth_time / total_apis if total_apis > 0 else 0
        
        print(f"Commands executed: {total_commands}")
        print(f"Total API calls: {total_apis}")
        print(f"Average OAuth time: {avg_oauth_time:.1f}ms")
        print()
        
        # Performance categorization
        if avg_oauth_time < 5:
            performance = "🚀 EXCELLENT"
            explanation = "Hitting tmpfs cache consistently"
        elif avg_oauth_time < 15:
            performance = "✅ GOOD"
            explanation = "Mostly tmpfs, occasional 1Password hits"
        elif avg_oauth_time < 50:
            performance = "⚠️ FAIR"
            explanation = "Mixed tmpfs/1Password access"
        else:
            performance = "❌ POOR"
            explanation = "Frequent 1Password access or system issues"
        
        print(f"Performance Rating: {performance}")
        print(f"Analysis: {explanation}")
        print()
        
        # Voice call quality assessment
        print("🎧 Voice Call Quality Assessment:")
        
        # Check for sub-10ms OAuth (voice quality threshold)
        fast_calls = sum(1 for log in self.call_logs if log['total_time'] < 50)
        fast_percentage = (fast_calls / total_commands) * 100
        
        if fast_percentage >= 90:
            quality = "🎯 EXCELLENT - Natural conversation flow"
        elif fast_percentage >= 70:
            quality = "✅ GOOD - Minor occasional pauses"
        elif fast_percentage >= 50:
            quality = "⚠️ FAIR - Noticeable delays"
        else:
            quality = "❌ POOR - Conversation feels broken"
        
        print(f"   {quality}")
        print(f"   Fast commands: {fast_calls}/{total_commands} ({fast_percentage:.0f}%)")
        
        # Recommendations
        print("\n🔧 Recommendations:")
        if avg_oauth_time < 10:
            print("   ✅ System is optimized for voice applications")
            print("   ✅ Continue current tmpfs + 1Password setup")
        else:
            print("   🔧 Consider investigating:")
            print("      - tmpfs cache hit rate")
            print("      - 1Password CLI performance")
            print("      - Network latency to OAuth providers")
            print("      - Process environment inheritance issues")


def benchmark_concurrent_access():
    """Test OAuth system under concurrent load (multiple voice sessions)."""
    print("\n🔀 Concurrent Access Benchmark")
    print("=" * 50)
    print("Simulating multiple voice sessions accessing tokens simultaneously...")
    print()
    
    results = []
    threads = []
    
    def worker_thread(thread_id):
        """Worker function for concurrent token access."""
        google = GoogleOAuth()
        thread_times = []
        
        for i in range(10):  # 10 token accesses per thread
            start = time.time()
            token = google.get_access_token()
            end = time.time()
            
            if token:
                access_time = (end - start) * 1000
                thread_times.append(access_time)
        
        results.append({
            'thread_id': thread_id,
            'times': thread_times,
            'avg_time': sum(thread_times) / len(thread_times) if thread_times else 0
        })
    
    # Start 5 concurrent threads
    for i in range(5):
        thread = threading.Thread(target=worker_thread, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Analyze results
    if results:
        all_times = []
        for result in results:
            all_times.extend(result['times'])
            print(f"Thread {result['thread_id']}: {result['avg_time']:.1f}ms avg")
        
        overall_avg = sum(all_times) / len(all_times)
        print(f"\nOverall average: {overall_avg:.1f}ms")
        print(f"Total accesses: {len(all_times)}")
        
        if overall_avg < 10:
            print("✅ Excellent concurrent performance")
        elif overall_avg < 25:
            print("⚠️ Good concurrent performance with minor contention")
        else:
            print("❌ Poor concurrent performance - investigate lock contention")


if __name__ == "__main__":
    print("OAuth Toolkit - Voice Call Performance Demo")
    print("=" * 60)
    print("This demo simulates OAuth token access patterns in voice applications.")
    print("Voice calls require sub-10ms OAuth access for natural conversation flow.")
    print()
    
    try:
        simulator = VoiceCallSimulator()
        simulator.run_voice_call_simulation()
        
        # Run concurrent access benchmark
        benchmark_concurrent_access()
        
        print("\n🎉 Voice call demo completed!")
        print("\nKey takeaways:")
        print("   - Sub-5ms OAuth = Excellent voice performance")
        print("   - 5-15ms OAuth = Acceptable with minor delays")
        print("   - 15ms+ OAuth = Noticeable conversation disruption")
        print("   - tmpfs cache is critical for voice applications")
        
    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        print("Make sure OAuth tokens are properly configured")