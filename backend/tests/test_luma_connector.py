from app.connectors.luma import LumaConnector


def test_luma_snapshot_date_converted_to_utc():
    # July → PDT (UTC-7): 5:00 PM local is 00:00 UTC the next day
    dt = LumaConnector._parse_date_from_snapshot("Thursday, July 30\n5:00 PM - 8:00 PM")
    assert (dt.month, dt.day, dt.hour) == (7, 31, 0)
