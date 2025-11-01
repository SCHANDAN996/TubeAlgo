#!/usr/bin/env python3
# fix_database.py
"""
Emergency database fix script for TubeAlgo
Run this directly on Render if tables are missing
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tubealgo import create_app, db

def fix_database():
    """Force create all database tables"""
    print("\n🔧 Starting emergency database fix...")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Drop all existing tables (be careful!)
            print("⚠️  Dropping existing tables...")
            db.drop_all()
            print("✅ Existing tables dropped")
            
            # Create all tables fresh
            print("🗄️  Creating all tables...")
            db.create_all()
            print("✅ All tables created")
            
            # Seed initial data
            from tubealgo import seed_plans
            seed_plans()
            print("✅ Initial data seeded")
            
            # Verify
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"\n✅ Database fixed! Found {len(tables)} tables:")
            for table in sorted(tables):
                print(f"   - {table}")
                
        except Exception as e:
            print(f"\n❌ Database fix failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

if __name__ == "__main__":
    success = fix_database()
    sys.exit(0 if success else 1)
