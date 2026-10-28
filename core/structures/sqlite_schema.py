"""SQLite schema extraction helpers."""

import re


class SQLiteSchemaParser:
    _CREATE_RE = re.compile(rb"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?", re.IGNORECASE)

    @classmethod
    def extract_tables(cls, data: bytes) -> list:
        results = []
        for match in cls._CREATE_RE.finditer(data):
            name = match.group(1).decode("ascii", errors="replace")
            # Capture the statement up to the next semicolon.
            stmt_start = match.start()
            semi = data.find(b";", stmt_start)
            if semi == -1:
                stmt_end = min(len(data), stmt_start + 512)
            else:
                stmt_end = semi + 1
            statement = data[stmt_start:stmt_end].decode("latin1")
            results.append(
                {
                    "name": name,
                    "address": match.start(),
                    "offset": match.start(),
                    "statement": statement,
                    "sql": statement,
                }
            )
        return results
