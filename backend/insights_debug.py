import io
import os
import uuid
import requests
import pandas as pd

base = 'http://127.0.0.1:8000'
email = f'user_{uuid.uuid4().hex[:8]}@example.test'
print('registering', email)
r = requests.post(f'{base}/register', json={'name':'Test User','email':email,'password':'secret123'})
print('register', r.status_code, r.text)
login = requests.post(f'{base}/login', json={'email':email,'password':'secret123'})
print('login', login.status_code, login.text)
token = login.json()['access_token']
df = pd.DataFrame({'segment':['A','B','A','B'], 'sales':[100,120,130,150], 'profit':[10,15,20,25]})
files = {'file': ('tmp_insights.csv', io.BytesIO(df.to_csv(index=False).encode('utf-8')), 'text/csv')}
upload = requests.post(f'{base}/upload', files=files, headers={'Authorization': 'Bearer ' + token})
print('upload', upload.status_code, upload.text)
resp = requests.get(f'{base}/insights', headers={'Authorization': 'Bearer ' + token})
print('insights_status', resp.status_code)
print(resp.text[:2000])
