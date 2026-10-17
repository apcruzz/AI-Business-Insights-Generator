# Executes analyst SQL against filtered rows; SQLite restrictions enforce read-only access.
"""Read-only SQLite tool over one filtered dataset. Never executes generated Python."""
import json
import sqlite3
import time


# Only these SQL functions are permitted; file access and extension loading are not available.
FUNCTIONS = {
    'sum', 'total', 'avg', 'min', 'max', 'count', 'round', 'abs', 'coalesce', 'ifnull', 'nullif',
    'strftime', 'date', 'datetime', 'julianday', 'unixepoch', 'substr', 'substring', 'length',
    'lower', 'upper', 'trim', 'ltrim', 'rtrim', 'replace', 'like', 'glob', 'instr', 'typeof',
    'row_number', 'rank', 'dense_rank', 'lag', 'lead', 'first_value', 'last_value',
}


class QueryTool:
    # Copy selected rows into an isolated in-memory sales table, then enable query restrictions.
    def __init__(self, frame):
        self.connection = sqlite3.connect(':memory:', cached_statements=0)
        frame.to_sql('sales', self.connection, index=False)
        self.connection.execute('PRAGMA query_only=ON')
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100000)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 8000)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 240)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 40)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 5)
        self.connection.set_authorizer(self.authorize)

    # SQLite calls this for each operation; allow sales reads and approved functions only.
    def authorize(self, action, first, second, database, origin):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and first == 'sales' and database == 'main':
            self.read_dataset = True
            self.read_columns.add(second)
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or '').lower() in FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    # Validate and execute a single query, recording which uploaded columns it actually reads.
    def run(self, sql, required_columns=()):
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 8000:
            raise ValueError('Provide one read-only SQL query, at most 8000 characters.')
        self.read_dataset = False
        self.read_columns = set()
        deadline, steps = time.monotonic() + 2, 0
        # Stop expensive queries by elapsed time or SQLite progress callbacks.
        def interrupt():
            nonlocal steps
            steps += 1
            return steps > 10000 or time.monotonic() > deadline
        self.connection.set_progress_handler(interrupt, 1000)
        try:
            cursor = self.connection.execute(sql)
            if not self.read_dataset:
                raise ValueError('Query must calculate from the sales table, not return invented constants.')
            # Require explicitly requested extra source dimensions to appear in the calculation.
            missing = set(required_columns) - self.read_columns
            if missing:
                raise ValueError('The question explicitly asks about these columns, but the query does not use them: ' + ', '.join(sorted(missing)))
            columns = [item[0] for item in cursor.description]
            # Fetch one extra row to signal truncation without returning an unbounded result.
            rows = cursor.fetchmany(31)
            if len(columns) > 12:
                raise ValueError('Select at most 12 output columns.')
            result = {'columns': columns, 'rows': [list(row) for row in rows[:30]], 'truncated': len(rows) > 30}
            if len(json.dumps(result, allow_nan=False)) > 14000:
                raise ValueError('Result too large. Aggregate the data or select fewer rows/columns.')
            return result
        except (sqlite3.Error, OverflowError) as error:
            raise ValueError('Query rejected or failed: ' + str(error)[:300]) from None
        # Remove the progress callback even after a failed query.
        finally:
            self.connection.set_progress_handler(None, 0)

    # Release the temporary database when the analyst request ends.
    def close(self):
        self.connection.close()
