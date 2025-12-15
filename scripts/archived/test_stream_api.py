"""测试 OLAV Orchestrator Stream API."""

import requests
import json

def test_orchestrator_stream():
    """测试 orchestrator stream 端点."""
    data = {
        'input': {
            'messages': [{'type': 'human', 'content': '查看所有设备接口状态'}]
        }
    }

    print('Sending query: 查看所有设备接口状态')
    print('=' * 50)

    resp = requests.post(
        'http://localhost:8001/orchestrator/stream',
        json=data,
        stream=True,
        timeout=120
    )

    print(f'Status: {resp.status_code}')
    
    response_content = ""
    event_count = 0
    all_data = []
    
    for line in resp.iter_lines():
        if line:
            text = line.decode()
            # Parse SSE format
            if text.startswith('data:'):
                try:
                    payload = json.loads(text[5:].strip())
                    all_data.append(payload)
                    
                    # Handle different data structures
                    if isinstance(payload, dict):
                        # LangServe format: check for messages in various locations
                        msgs = payload.get('messages', [])
                        
                        # Check nested structures
                        if not msgs:
                            for key in ['output', 'route_to_workflow', 'execute_workflow', '__end__']:
                                nested = payload.get(key, {})
                                if isinstance(nested, dict):
                                    msgs = nested.get('messages', [])
                                    if msgs:
                                        break
                        
                        for msg in msgs:
                            content = None
                            if isinstance(msg, dict):
                                content = msg.get('content')
                            elif hasattr(msg, 'content'):
                                content = msg.content
                            
                            if content and content != response_content and len(content) > len(response_content):
                                response_content = content
                                print(f"\n📝 Response update:")
                                print(content[:800])
                                if len(content) > 800:
                                    print("...")
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
            elif text.startswith('event:'):
                event_type = text[6:].strip()
                event_count += 1
                if event_type not in ['metadata', 'data']:
                    print(f'📡 Event: {event_type}')
    
    print(f'\n✅ Completed with {event_count} events, {len(all_data)} data chunks')
    
    if response_content:
        print(f'\n📋 Final response length: {len(response_content)} chars')
    else:
        print("\n⚠️ No response content extracted")
        if all_data:
            print("Raw data samples:")
            for i, d in enumerate(all_data[:3]):
                print(f"  [{i}]: {str(d)[:200]}")

if __name__ == '__main__':
    test_orchestrator_stream()
