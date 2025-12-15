"""Test script to understand LangGraph event structure."""
import asyncio
from langgraph.graph import StateGraph, END
from typing import TypedDict

class State(TypedDict):
    messages: list

async def node1(state):
    return {'messages': ['hello']}

async def node2(state):
    return {'messages': state['messages'] + ['world']}

graph = StateGraph(State)
graph.add_node('node1', node1)
graph.add_node('node2', node2)
graph.set_entry_point('node1')
graph.add_edge('node1', 'node2')
graph.add_edge('node2', END)
app = graph.compile()

async def main():
    print("LangGraph Event Structure Test")
    print("=" * 50)
    async for event in app.astream_events({'messages': []}, version='v2'):
        event_type = event.get('event')
        name = event.get('name')
        tags = event.get('tags', [])
        metadata = event.get('metadata', {})
        langgraph_node = metadata.get('langgraph_node')
        print(f"Event: {event_type:25} | Name: {name:15} | Node: {langgraph_node} | Tags: {tags}")

asyncio.run(main())
