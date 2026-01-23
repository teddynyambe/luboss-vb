#!/bin/bash
# Export old MySQL schema, FK relationships, and row counts

MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DATABASE="${MYSQL_DATABASE:-village_bank}"

OUTPUT_DIR="docs/db"
mkdir -p "$OUTPUT_DIR"

# Export schema
echo "Exporting schema..."
mysqldump -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  --no-data --routines --triggers "$MYSQL_DATABASE" > "$OUTPUT_DIR/old_schema.sql"

# Export foreign key relationships
echo "Exporting foreign key relationships..."
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT 
    CONCAT('ALTER TABLE ', TABLE_NAME, ' ADD CONSTRAINT ', CONSTRAINT_NAME, 
           ' FOREIGN KEY (', COLUMN_NAME, ') REFERENCES ', 
           REFERENCED_TABLE_NAME, '(', REFERENCED_COLUMN_NAME, ');') as fk_statement
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = '$MYSQL_DATABASE'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
" > "$OUTPUT_DIR/old_fk.txt"

# Export row counts (no PII)
echo "Exporting row counts..."
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT 
    TABLE_NAME,
    TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = '$MYSQL_DATABASE'
ORDER BY TABLE_NAME;
" > "$OUTPUT_DIR/old_row_counts.txt"

echo "Export complete. Files saved to $OUTPUT_DIR/"
