import sys
import base64
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Setup params
base_url = "http://localhost:18090"
email = "admin@shijian.local"
password = "test-long-password-12345"

def login_admin():
    req = Request(
        f"{base_url}/api/collections/_superusers/auth-with-password",
        data=json.dumps({"identity": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())["token"]

try:
    print("Logging in...")
    token = login_admin()
    print("Login successful, token retrieved.")
    
    # Let's create a body with some dummy base64 data (e.g. 5MB)
    size_mb = 5
    dummy_bytes = b"X" * (size_mb * 1024 * 1024)
    b64data = base64.b64encode(dummy_bytes).decode("ascii")
    
    body = {
        "user": "ftflub2cpnun6gd", # our registered local@test.com user id
        "source_url": "https://attachment.local/debug-large-file.txt",
        "title": "debug-large-file.txt",
        "filename": "debug-large-file.txt",
        "content_md": "",
        "images": [],
        "kind": "attachment",
        "attachment_filename": "debug-large-file.txt",
        "attachment_mime": "text/plain",
        "attachment_b64": b64data,
        "delivered": 0,
    }
    
    print(f"Sending request to create note record with {size_mb}MB payload...")
    req = Request(
        f"{base_url}/api/collections/notes/records",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    with urlopen(req, timeout=60) as resp:
        print("Success! Status code:", resp.status)
        print("Response:", resp.read().decode()[:200])

except HTTPError as e:
    print("HTTPError occurred! Status:", e.code)
    print("Response body:", e.read().decode())
except Exception as e:
    print("Error occurred:", str(e))
