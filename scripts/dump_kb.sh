#!/usr/bin/env bash
# Regenerate the committed knowledge-base dump from the running database.
#
#   ./scripts/dump_kb.sh
#
# The flags are not optional:
#   --schema=football --schema=prose  monitoring is excluded on purpose; its
#                                     rows are back-dated and go stale.
#   --no-owner --no-privileges        the restoring user comes from the
#                                     reviewer's .env and will not match ours.
#
# Re-run this after any deliberate rebuild of the knowledge base — in
# particular after a change to chunking or the embedding model, which would
# otherwise leave the committed dump quietly describing a corpus that no longer
# exists.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a && . ./.env && set +a

OUT=data/kb.sql.gz
mkdir -p data

docker exec "${POSTGRES_CONTAINER:-wc2026-postgres}" pg_dump \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --schema=football --schema=prose \
    --no-owner --no-privileges \
  | gzip -9 > "$OUT"

echo "-> $OUT ($(du -h "$OUT" | cut -f1))"
