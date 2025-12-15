"""Check NetBox devices via API."""
import os
import requests

def main():
    url = os.getenv('NETBOX_URL', 'http://localhost:8080')
    token = os.getenv('NETBOX_TOKEN')
    
    headers = {'Authorization': f'Token {token}'}
    # First check all devices (without tag filter)
    resp = requests.get(
        f'{url}/api/dcim/devices/', 
        headers=headers, 
        verify=False
    )
    data = resp.json()
    
    print(f"Total devices: {data.get('count', 0)}")
    for dev in data.get('results', []):
        ip = dev.get('primary_ip4', {}).get('address', 'N/A') if dev.get('primary_ip4') else 'N/A'
        role = dev.get('role', {}).get('name', 'N/A') if dev.get('role') else 'N/A'
        platform = dev.get('platform', {}).get('name', 'N/A') if dev.get('platform') else 'N/A'
        print(f"  {dev['name']}: {ip} (role={role}, platform={platform})")

if __name__ == "__main__":
    main()
