"""Add a device tag to all devices in NetBox.

Uses NETBOX_DEVICE_TAG (default: 'olav-managed').
"""
import os
import requests

def main():
    url = os.getenv('NETBOX_URL', 'http://localhost:8080')
    token = os.getenv('NETBOX_TOKEN')
    tag_name = os.getenv("NETBOX_DEVICE_TAG") or "olav-managed"
    
    headers = {'Authorization': f'Token {token}', 'Content-Type': 'application/json'}
    
    # First, ensure the tag exists
    print(f"Checking/creating '{tag_name}' tag...")
    tag_check = requests.get(f'{url}/api/extras/tags/', headers=headers, params={'name': tag_name})
    if tag_check.json().get('count', 0) == 0:
        tag_create = requests.post(f'{url}/api/extras/tags/', headers=headers, json={
            'name': tag_name,
            'slug': tag_name.strip().lower(),
            'color': '0088ff',
            'description': 'Device managed by OLAV system'
        })
        if tag_create.status_code in (200, 201):
            tag_id = tag_create.json()['id']
            print(f"Created tag '{tag_name}' with ID {tag_id}")
        else:
            print(f"Failed to create tag: {tag_create.text}")
            return
    else:
        tag_id = tag_check.json()['results'][0]['id']
        print(f"Tag '{tag_name}' already exists with ID {tag_id}")
    
    # Get all devices
    devices_resp = requests.get(f'{url}/api/dcim/devices/', headers=headers)
    devices = devices_resp.json().get('results', [])
    
    print(f"\nUpdating {len(devices)} devices...")
    for dev in devices:
        device_id = dev['id']
        device_name = dev['name']
        current_tags = [t['id'] for t in dev.get('tags', [])]
        
        if tag_id in current_tags:
            print(f"  {device_name}: already has {tag_name} tag")
            continue
        
        # Add the tag
        current_tags.append(tag_id)
        patch_resp = requests.patch(
            f'{url}/api/dcim/devices/{device_id}/',
            headers=headers,
            json={'tags': current_tags}
        )
        if patch_resp.status_code in (200, 201):
            print(f"  {device_name}: added {tag_name} tag ✓")
        else:
            print(f"  {device_name}: failed to add tag - {patch_resp.text[:100]}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()
