# create_tables.py
"""
Database table creation script for TubeAlgo
This ensures all tables are created properly on Render deployment
"""

import sys
import traceback
from tubealgo import create_app, db

def create_all_tables():
    """Create all database tables with proper error handling"""
    print("=" * 60)
    print("TUBEALGO DATABASE INITIALIZATION")
    print("=" * 60)
    
    try:
        # Create Flask app with configuration
        app = create_app()
        
        with app.app_context():
            print("\n1. Creating database connection...")
            
            # Test database connection
            from sqlalchemy import text
            try:
                result = db.session.execute(text('SELECT 1'))
                print("   ✓ Database connection successful")
            except Exception as e:
                print(f"   ✗ Database connection failed: {e}")
                raise
            
            print("\n2. Importing all models...")
            # Import all models to ensure they're registered with SQLAlchemy
            from tubealgo.models import (
                User, 
                YouTubeChannel,
                Competitor, 
                ChannelSnapshot, 
                VideoSnapshot, 
                ContentIdea, 
                SubscriptionPlan,
                Payment,
                SystemLog, 
                DashboardCache,
                Goal, 
                ThumbnailTest,
                SearchHistory,
                Coupon,
                ApiCache,
                APIKeyStatus,
                SiteSetting
            )
            print("   ✓ All models imported successfully")
            
            print("\n3. Creating database tables...")
            # Create all tables
            db.create_all()
            print("   ✓ Database tables created successfully")
            
            print("\n4. Verifying tables...")
            # Verify critical tables exist
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            critical_tables = ['user', 'you_tube_channel', 'subscription_plan', 'competitor']
            missing_tables = [t for t in critical_tables if t not in tables]
            
            if missing_tables:
                print(f"   ✗ Missing critical tables: {missing_tables}")
                print(f"   Available tables: {', '.join(sorted(tables))}")
                raise Exception(f"Critical tables not created: {missing_tables}")
            else:
                print(f"   ✓ All critical tables verified")
                print(f"   Total tables created: {len(tables)}")
                print(f"   Tables: {', '.join(sorted(tables))}")
            
            print("\n5. Seeding initial data...")
            # Seed subscription plans if needed
            from tubealgo import seed_plans
            seed_plans()
            print("   ✓ Initial data seeded")
            
            print("\n" + "=" * 60)
            print("DATABASE INITIALIZATION COMPLETE!")
            print("=" * 60)
            return True
            
    except Exception as e:
        print("\n" + "=" * 60)
        print("DATABASE INITIALIZATION FAILED!")
        print("=" * 60)
        print(f"\nError Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("\nFull Traceback:")
        print("-" * 40)
        traceback.print_exc()
        print("-" * 40)
        return False

if __name__ == "__main__":
    success = create_all_tables()
    
    if not success:
        print("\n⚠️  Build will fail due to database initialization error")
        sys.exit(1)
    else:
        print("\n✅ Database is ready for application deployment")
        sys.exit(0)
