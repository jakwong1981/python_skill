# 1. Create a virtual environment inside your project folder
python3 -m venv venv

# 2. Activate it (your shell prompt will show (venv))
source venv/bin/activate

# 3. Install the required Google libraries
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# 4. Run your script
python parser_gmail_bill.py
