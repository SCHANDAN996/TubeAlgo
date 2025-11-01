# tubealgo/models/youtube_models.py

from .. import db
from datetime import datetime

class YouTubeChannel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    channel_id_youtube = db.Column(db.String(100), unique=True, nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))

class ChannelSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_db_id = db.Column(db.Integer, db.ForeignKey('you_tube_channel.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    subscribers = db.Column(db.Integer, nullable=False)
    views = db.Column(db.BigInteger, nullable=False)
    video_count = db.Column(db.Integer, nullable=False)
    
    # --- THIS IS THE CORRECTED LINE ---
    channel = db.relationship('YouTubeChannel', backref=db.backref('snapshots', cascade="all, delete-orphan"))
    
    __table_args__ = (db.UniqueConstraint('channel_db_id', 'date', name='_channel_date_uc'),)

class Competitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    channel_id_youtube = db.Column(db.String(100), nullable=False)
    channel_title = db.Column(db.String(200), nullable=False)
    thumbnail_url = db.Column(db.String(255))
    position = db.Column(db.Integer, nullable=False)
    last_known_video_id = db.Column(db.String(50), nullable=True)
    
    notified_trending_videos = db.Column(db.Text, nullable=True)


class ThumbnailTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.String(50), nullable=False, index=True)
    
    status = db.Column(db.String(50), nullable=False, default='pending') 
    
    thumbnail_a_path = db.Column(db.String(255), nullable=False)
    thumbnail_b_path = db.Column(db.String(255), nullable=False)
    result_a_ctr = db.Column(db.Float, nullable=True)
    result_b_ctr = db.Column(db.Float, nullable=True)
    winner = db.Column(db.String(10), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    test_start_time = db.Column(db.DateTime, nullable=True)
    switch_time = db.Column(db.DateTime, nullable=True)
    test_end_time = db.Column(db.DateTime, nullable=True)
    
    user = db.relationship('User', backref='thumbnail_tests')

class VideoSnapshot(db.Model):
    """Stores historical view counts of competitor videos to track trends."""
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    view_count = db.Column(db.BigInteger, nullable=False)

    __table_args__ = (db.UniqueConstraint('video_id', 'timestamp', name='_video_timestamp_uc'),)