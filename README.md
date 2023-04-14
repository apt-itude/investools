# Investools

# Setup

## Google Sheets Auth
Follow [these instructions](https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id)

### Troubleshooting
If you get:
```
google.auth.exceptions.RefreshError: ('invalid_grant: Bad Request', {'error': 'invalid_grant', 'error_description': 'Bad Request'})
```

Then remove this file:
```
~/.config/gspread/authorized_user.json
```

And try again.

## Environment

### Tiingo
1. Get API token from [here](https://www.tiingo.com/account/api/token)
2. Set `TIINGO_API_KEY` to that value

### Google Sheets
1. Open Investools Google Sheet
2. Copy the ID from the URL (format: `https://docs.google.com/spreadsheets/d/<id>/edit`)
3. Set `INVESTOOLS_GOOGLE_SHEET_ID` to that value
