import stealth_requests as requests

resp = requests.get('https://kick.com/api/v2/channels/daisyks')
print(resp.raise_for_status)

