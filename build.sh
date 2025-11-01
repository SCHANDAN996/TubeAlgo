#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== TubeAlgo Build Process Started ==="

# Step 1: Upgrade pip first
echo "🔄 Upgrading pip..."
pip install --upgrade pip

# Step 2: Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Step 3: Build Tailwind CSS and JavaScript
echo "🎨 Building assets..."
npm run build

# Step 4: Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Step 5: Create database tables
echo "🗄️ Creating database tables..."
python create_tables.py

echo "🎉 Build process completed successfully!"
