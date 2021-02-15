import gspread

from investools import model


_GOOGLE_OAUTH_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_client():
    return gspread.oauth(scopes=_GOOGLE_OAUTH_SCOPES)


def build_portfolio(sheet):
    data = {
        worksheet_title: sheet.worksheet(worksheet_title).get_all_records(
            value_render_option="UNFORMATTED_VALUE"
        )
        for worksheet_title in ["Allocations", "Accounts", "Assets"]
    }
    for account_record in data["Accounts"]:
        name = account_record["Name"]
        try:
            lots_worksheet = sheet.worksheet(f"Lots: {name}")
        except gspread.exceptions.WorksheetNotFound:
            lot_records = []
        else:
            lot_records = lots_worksheet.get_all_records(
                value_render_option="UNFORMATTED_VALUE"
            )
        account_record["Asset Lots"] = lot_records

    config_worksheet = sheet.worksheet("Config")
    data["Config"] = _rows_to_dict(config_worksheet)

    return model.Portfolio.parse_obj(data)


def _rows_to_dict(worksheet):
    return {
        row[0]: row[1]
        for row in worksheet.get_all_values(value_render_option="UNFORMATTED_VALUE")
    }
