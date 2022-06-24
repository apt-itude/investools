# Investools

## Fixing Google Sheet auth errors
If you get:
```
google.auth.exceptions.RefreshError: ('invalid_grant: Bad Request', {'error': 'invalid_grant', 'error_description': 'Bad Request'})
```

Then remove this file:
```
~/.config/gspread/authorized_user.json
```

And try again.
