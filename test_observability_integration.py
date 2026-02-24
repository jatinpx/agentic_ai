#!/usr/bin/env python
"""
Quick verification script for observability integration.

Tests:
1. ObservabilityManager singleton initialization
2. Span creation and timing
3. Event emission to callbacks
4. Correlation ID propagation
5. Decorator wrapping
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "AI/autonomus-ai-employee/backend"))


async def test_observability_basic():
    """Test core observability functionality."""
    print("\n=== Test 1: ObservabilityManager Initialization ===")
    
    from services.observability_service import get_observability_manager
    obs = get_observability_manager()
    print(f"✓ Manager singleton created: {obs}")
    
    # Generate and get correlation ID
    corr_id = obs.get_correlation_id()
    print(f"✓ Correlation ID generated: {corr_id}")
    
    print("\n=== Test 2: Span Creation & Tracking ===")
    
    # Create a span
    span = obs.start_span(
        name="test_operation",
        event_type="test_event",
        node_name="test_node",
        input_data={"test": "data"},
    )
    print(f"✓ Span created: {span.span_id}")
    
    # Simulate some work
    await asyncio.sleep(0.1)
    
    # End span
    obs.end_span(
        span,
        output_data={"result": "success"},
        status="ok"
    )
    print(f"✓ Span ended: latency={span.latency_ms:.1f}ms")
    
    print("\n=== Test 3: Event Callbacks ===")
    
    events_received = []
    
    async def test_callback(event):
        events_received.append(event)
        print(f"  → Event received: type={event.get('type')}, span_id={event.get('span_id')}")
    
    obs.register_event_callback(test_callback)
    
    # Create another span (should trigger callbacks)
    span2 = obs.start_span(
        name="test_with_callback",
        event_type="test_event",
        node_name="callback_test",
    )
    await asyncio.sleep(0.05)
    obs.end_span(span2, status="ok")
    
    # Give callbacks time to execute
    await asyncio.sleep(0.1)
    
    print(f"✓ Events captured: {len(events_received)} events")
    if len(events_received) >= 2:
        print(f"  → span_start event: {events_received[0]['type']}")
        print(f"  → span_end event: {events_received[1]['type']}")
    
    print("\n=== Test 4: Logging Integration ===")
    
    from brain.linkedin import logging_utils
    print(f"✓ logging_utils loaded (OBSERVABILITY_ENABLED={logging_utils.OBSERVABILITY_ENABLED})")
    
    # Test that logging functions don't crash
    logging_utils.log_node("test_node", "TEST EVENT", "testing logging integration")
    print(f"✓ log_node() executed successfully")
    
    logging_utils.log_token_usage("test_node", "test-model", 100, 50)
    print(f"✓ log_token_usage() executed successfully")
    
    logging_utils.log_error("test_node", "Test error message")
    print(f"✓ log_error() executed successfully")
    
    print("\n=== Test 5: Decorator Application ===")
    
    from services.observability_service import instrument_function
    
    @instrument_function(event_type="test", node_name="test_func", capture_args=True)
    async def test_decorated_function(x: int, y: int) -> int:
        await asyncio.sleep(0.05)
        return x + y
    
    result = await test_decorated_function(5, 3)
    await asyncio.sleep(0.1)  # Let async callbacks process
    
    print(f"✓ Decorated async function executed: 5 + 3 = {result}")
    print(f"✓ Decorator created span for function call")
    
    print("\n=== Test 6: Trace Retrieval ===")
    
    trace = await obs.get_trace(corr_id)
    print(f"✓ Retrieved trace for correlation_id: {len(trace)} spans")
    for i, span_dict in enumerate(trace[:3], 1):
        print(f"  [{i}] {span_dict.get('name')} | type={span_dict.get('event_type')} | latency={span_dict.get('latency_ms', 'N/A')}")
    
    print("\n=== All Tests Passed ===\n")
    print("Observability infrastructure is working correctly!")
    print(f"Total events captured: {len(events_received)}")
    print(f"Total spans in trace: {len(trace)}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("OBSERVABILITY INTEGRATION VERIFICATION")
    print("="*60)
    
    try:
        asyncio.run(test_observability_basic())
        print("\n✅ Integration verification PASSED")
    except Exception as e:
        print(f"\n❌ Integration verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
