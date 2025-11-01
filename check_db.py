#!/usr/bin/env python3
# check_db.py
"""Quick database health check for TubeAlgo"""

from tubealgo import create_app, db
from sqlalchemy import text, inspect

def check_database():
    app = create_app()
    
    with app.app_context():
        print("\n🔍 Database Health Check\n" + "=" * 40)
        
        # Check connection
        try:
            db.session.execute(text('SELECT 1'))
            print("✅ Database connection: OK")
        except Exception as e:
            print(f"❌ Database connection: FAILED - {e}")
            return False
        
        # Check tables
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if not tables:
            print("❌ No tables found in database!")
            return False
        
        print(f"✅ Tables found: {len(tables)}")
        
        # Check critical tables
        critical = ['user', 'channel', 'subscription_plan', 'competitor']
        missing = [t for t in critical if t not in tables]
        
        if missing:
            print(f"❌ Missing critical tables: {missing}")
            return False
        else:
            print("✅ All critical tables present")
        
        # Check user count
        try:
            from tubealgo.models import User
            user_count = User.query.count()
            print(f"ℹ️  Total users in database: {user_count}")
        except:
            pass
        
        print("\n" + "=" * 40)
        print("✨ Database is healthy!\n")
        return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if check_database() else 1)
