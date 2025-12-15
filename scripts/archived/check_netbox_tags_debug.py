import requests
import json

NETBOX_URL = 'http://localhost:8080'
TOKEN = '0123456789abcdef0123456789abcdef01234567'

headers = {
    'Authorization': f'Token {TOKEN}',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

def check_tags():
    print(f'Checking tags at {NETBOX_URL}...')
    try:
        response = requests.get(f'{NETBOX_URL}/api/extras/tags/', headers=headers)
        response.raise_for_status()
        data = response.json()
        tags = [t['slug'] for t in data['results']]
        print(f'Available tags: {tags}')
        
        for tag in ['suzieq', 'olav-managed']:
            if tag in tags:
                print(f'Tag \'{tag}\' found.')
            else:
                print(f'Tag \'{tag}\' NOT found.')
            
    except Exception as e:
        print(f'Error checking tags: {e}')

def check_devices(tag):
    print(f'\nChecking devices with tag \'{tag}\'...')
    try:
        response = requests.get(f'{NETBOX_URL}/api/dcim/devices/?tag={tag}', headers=headers)
        response.raise_for_status()
        data = response.json()
        count = data['count']
        print(f'Found {count} devices with tag \'{tag}\'.')
        for device in data['results']:
            print(f' - {device['name']} ({device['primary_ip']['address'] if device['primary_ip'] else 'No IP'})')
            
    except Exception as e:
        print(f'Error checking devices: {e}')

if __name__ == '__main__':
    check_tags()
    check_devices('suzieq')
    check_devices('olav-managed')
