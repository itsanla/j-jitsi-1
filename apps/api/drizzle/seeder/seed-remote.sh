#!/bin/bash

# Script untuk seeding database remote (production)
# Usage: ./seed-remote.sh

set -e

echo "🚀 Starting REMOTE database seeding..."
echo ""
echo "⚠️  WARNING: This will seed data to PRODUCTION database!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "❌ Seeding cancelled."
  exit 0
fi

echo ""
echo "Proceeding with remote seeding..."
echo ""

SEEDERS=(
  "01_events.sql"
  "02_quotas.sql"
  "03_promo_codes.sql"
  "04_users.sql"
)

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Counter for progress
TOTAL=${#SEEDERS[@]}
CURRENT=0

# Execute each seeder
for seeder in "${SEEDERS[@]}"; do
  CURRENT=$((CURRENT + 1))
  echo "[$CURRENT/$TOTAL] Executing $seeder on REMOTE..."
  
  if [ -f "$SCRIPT_DIR/$seeder" ]; then
    pnpm wrangler d1 execute DB --remote --file="drizzle/seeder/$seeder"
    echo "✅ $seeder completed"
    echo ""
    
    # Add a small delay to avoid rate limiting
    sleep 1
  else
    echo "⚠️  Warning: $seeder not found, skipping..."
    echo ""
  fi
done

echo "✨ Remote seeding completed successfully!"
echo ""
echo "Your production database has been seeded."
