# Online License Activation System

Protect your software so only people with a valid key from you can use it.

## Features

- Admin panel to generate, disable, and delete license keys
- See which computers activated each key
- Limit how many computers one key can activate
- Online activation API for your Python apps
- Works on free hosting (Render.com)

---

## 1. Deploy the Server for FREE on Render.com

### Step-by-step

1. Create a free account at [https://render.com](https://render.com)

2. Click **New** → **Web Service**

3. Connect your GitHub account (or use the "Deploy from Git" option later)

4. Easiest method (no GitHub needed):
   - Create a new GitHub repository
   - Upload all files from this `license-online` folder
   - Then in Render: New → Web Service → select that repository

5. Settings in Render:
   - **Name**: `my-license-server` (or any name)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free

6. Add Environment Variables (important!):
   - `ADMIN_PASSWORD` = a strong password you will use to login
   - `LICENSE_SECRET` = a long random secret (at least 32 characters)
   - `FLASK_SECRET` = another random string

7. Click **Create Web Service**

8. Wait 1–3 minutes. When it is live you will get a URL like:
   `https://my-license-server.onrender.com`

9. Open that URL → login with the `ADMIN_PASSWORD` you set.

---

## 2. Protect Your Python App

1. Copy the file `client/license_client.py` into your project.

2. Open it and change these two lines:

```python
SERVER_URL = "https://my-license-server.onrender.com"   # your real Render URL
PRODUCT_ID = "MyApp-Pro"                                # your product name
```

3. At the very beginning of your main program add:

```python
from license_client import check_license
import sys

if not check_license():
    input("Press Enter to exit...")
    sys.exit(1)

# Your real application starts here
print("Welcome! Licensed version running.")
```

---

## 3. How the full process works

1. Customer runs your app → sees their Machine ID
2. Customer sends you the Machine ID (or just asks for a key)
3. You open the Admin panel → Generate a new key
4. You send the key to the customer
5. Customer enters the key → app contacts your server → activates
6. Later you can Disable the key anytime from the admin panel

---

## Important Notes about Free Tier

- On Render free plan the server **goes to sleep** after ~15 minutes of no activity.
- The first request after sleeping can take 15–40 seconds (cold start).
- After that it is fast again.
- This is normal and acceptable for most indie apps.

- SQLite database is used. On free Render the database is reset if the service is fully restarted for a long time. For serious use later you can upgrade to a free PostgreSQL database.

---

## Local Testing

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000  
Default password: `admin123`
