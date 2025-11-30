"""Check syslog for OSPF events."""
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    from olav.tools.syslog_tool import syslog_search
    
    # Search for OSPF events
    result = await syslog_search.ainvoke({
        'keyword': 'OSPF|neighbor|adjacency',
        'start_time': 'now-1h',
        'limit': 20,
    })
    
    data = result.get("data", [])
    print(f'Found {len(data)} OSPF events:')
    for entry in data:
        ts = entry.get("timestamp", "")
        msg = entry.get("message", "")[:100]
        print(f'  {ts}: {msg}')

asyncio.run(main())
