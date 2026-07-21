"""Small raw-frame factories; synthetic rows are never formal project results."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

RAW_COLUMNS = (
    "index",
    "Date",
    "Time",
    "Global_active_power",
    "Global_reactive_power",
    "Voltage",
    "Global_intensity",
    "Sub_metering_1",
    "Sub_metering_2",
    "Sub_metering_3",
)


def raw_minute_frame(
    timestamps: Sequence[pd.Timestamp],
    *,
    missing_positions: set[int] | None = None,
    four_digit_year_positions: set[int] | None = None,
) -> pd.DataFrame:
    """Create a raw-contract DataFrame with optional fully missing measurement rows."""
    missing = missing_positions or set()
    four_digit = four_digit_year_positions or set()
    rows: list[dict[str, str]] = []
    for index, timestamp in enumerate(timestamps):
        year_text = str(timestamp.year) if index in four_digit else str(timestamp.year)[2:]
        date_text = f"{timestamp.day}/{timestamp.month}/{year_text}"
        row = {
            "index": str(index),
            "Date": date_text,
            "Time": f"{timestamp.hour}:{timestamp.minute:02d}:{timestamp.second:02d}",
            "Global_active_power": "1.2",
            "Global_reactive_power": "0.1",
            "Voltage": "240.0",
            "Global_intensity": "5.0",
            "Sub_metering_1": "1.0",
            "Sub_metering_2": "2.0",
            "Sub_metering_3": "3.0",
        }
        if index in missing:
            for column in RAW_COLUMNS[3:]:
                row[column] = "?" if column != "Sub_metering_3" else ""
        rows.append(row)
    return pd.DataFrame(rows, columns=RAW_COLUMNS)
