"""Interaction logging for the agent — conversations + feedback in Postgres.

Reference: llm-zoomcamp 05-monitoring/code (db_init.py, db_save.py, db_feedback.py).
"""

from datetime import datetime

DB_TIMEZONE = datetime.now().astimezone().tzinfo
