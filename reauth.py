"""
Re-authenticate YouTube OAuth and save new token.
Run once locally: python3 reauth.py
"""
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("youtube_token.pickle", "wb") as f:
    pickle.dump(creds, f)

# Verify: fetch channel info
youtube = build("youtube", "v3", credentials=creds)
resp = youtube.channels().list(part="snippet", mine=True).execute()
for ch in resp.get("items", []):
    print(f"✅ 已授權頻道：{ch['snippet']['title']} ({ch['id']})")

print("\n完成！youtube_token.pickle 已更新。")
print("接下來把新 token 上傳到 GitHub Secrets。")
