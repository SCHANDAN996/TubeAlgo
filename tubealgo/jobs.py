# tubealgo/jobs.py


import traceback
import os
from datetime import date, timedelta, datetime
from flask import current_app
import time
import random

from . import db, celery
# --- बदलाव यहाँ: ChannelSnapshot और VideoSnapshot को इम्पोर्ट किया गया ---
from .models import User, Competitor, ChannelSnapshot, DashboardCache, log_system_event, ThumbnailTest, VideoSnapshot #
from .services.video_fetcher import get_latest_videos
from .services.channel_fetcher import analyze_channel
from .services.notification_service import send_telegram_message
from .services.ai_service import get_ai_video_suggestions, generate_motivational_suggestion
from .routes.utils import get_credentials
from .services.youtube_manager import set_video_thumbnail, get_single_video, update_video_details
from .services.analytics_service import get_video_ctr
from celery.schedules import crontab # crontab को इम्पोर्ट किया गया


@celery.task
def take_daily_snapshots():
    """हर दिन सभी उपयोगकर्ताओं के चैनलों के आँकड़ों का स्नैपशॉट लेता है।"""
    print("Celery Task: Running job to take daily channel snapshots...")
    users_with_channels = User.query.join(User.channel).all() #

    for user in users_with_channels: #
        try: #
            channel_data = analyze_channel(user.channel.channel_id_youtube) #
            if 'error' in channel_data: #
                log_system_event( #
                     message=f"Could not fetch channel data for snapshot: {user.email}", #
                    log_type='WARNING', #
                    details={'error': channel_data['error']} #
                ) #
                continue #

            today_snapshot = ChannelSnapshot.query.filter_by( #
                channel_db_id=user.channel.id, #
                date=date.today() #
            ).first() #

            if today_snapshot: #
                today_snapshot.subscribers = channel_data.get('Subscribers', 0) #
                today_snapshot.views = channel_data.get('Total Views', 0) #
                today_snapshot.video_count = channel_data.get('Video Count', 0) #
            else: #
                new_snapshot = ChannelSnapshot( #
                    channel_db_id=user.channel.id, #
                    date=date.today(), #
                    subscribers=channel_data.get('Subscribers', 0), #
                    views=channel_data.get('Total Views', 0), #
                    video_count=channel_data.get('Video Count', 0) #
                ) #
                db.session.add(new_snapshot) #

            db.session.commit() #
            print(f"Successfully took snapshot for user: {user.email}") #

        except Exception as e: #
            db.session.rollback() #
            tb_str = traceback.format_exc() #
            log_system_event( #
                 message=f"Error taking snapshot for user {user.email}", #
                log_type='ERROR', #
                details={'error': str(e), 'traceback': tb_str} #
            ) #

    print("Celery Task: Finished taking daily snapshots.") #


@celery.task
def check_for_new_videos():
    """प्रतियोगियों के नए वीडियो की जांच करता है और टेलीग्राम पर सूचित करता है।"""
    print("Celery Task: Running job to check for new videos...") #
    users_with_telegram = User.query.filter(User.telegram_chat_id.isnot(None), User.telegram_notify_new_video == True).all() #

    for user in users_with_telegram: #
        print(f"Checking competitors for user: {user.email}") #
        competitors = user.competitors.all() #

        for comp in competitors: #
            try: #
                latest_videos_data = get_latest_videos(comp.channel_id_youtube, max_results=1) #

                if not latest_videos_data or not latest_videos_data.get('videos'): #
                    continue #

                latest_video = latest_videos_data['videos'][0] #
                video_id = latest_video['id'] #
                video_title = latest_video['title'] #

                if not comp.last_known_video_id: #
                    comp.last_known_video_id = video_id #
                    db.session.commit() #
                    continue #

                if comp.last_known_video_id != video_id: #
                    print(f"Found new video for {comp.channel_title}: {video_title}") #

                    comp.last_known_video_id = video_id #
                    db.session.commit() #

                    message = ( #
                        f"🚀 *New Video Alert!*\n\n" #
                        f"Your competitor *{comp.channel_title}* just uploaded a new video!\n\n" #
                        f"*Video Title:*\n \"{video_title}\"\n\n" #
                        f"_[Watch on YouTube](https://www.youtube.com/watch?v={video_id})_" #
                    ) #

                    if user.telegram_notify_ai_suggestion: #
                        ai_suggestion = generate_motivational_suggestion(video_title) #
                        message += f"\n\n---\n💡 *Your Motivational AI Assistant:*\n\n{ai_suggestion}" #

                    send_telegram_message(user.telegram_chat_id, message) #

            except Exception as e: #
                db.session.rollback() #
                tb_str = traceback.format_exc() #
                log_system_event( #
                    message=f"Error checking new videos for competitor {comp.channel_title}", #
                    log_type='ERROR', #
                    details={'user_id': user.id, 'competitor_id': comp.id, 'error': str(e), 'traceback': tb_str} #
                ) #

    print("Celery Task: Finished checking for new videos.") #


@celery.task
def update_all_dashboards():
    """सभी यूज़र्स के लिए डैशबोर्ड डेटा को बैकग्राउंड में रीफ्रेश और कैश करता है।"""
    print("Celery Task: Running job to update all user dashboards...") #
    users_with_channels = User.query.join(User.channel).all() #

    for user in users_with_channels: #
        try: #
            print(f"Updating dashboard for user: {user.email}") #
            channel_id = user.channel.id #

            channel_data = analyze_channel(user.channel.channel_id_youtube) #
            if 'error' in channel_data: continue #

            kpis = {'subscribers': channel_data.get('Subscribers', 0), 'views': channel_data.get('Total Views', 0), 'videos': channel_data.get('Video Count', 0)} #

            today = date.today() #
            start_date = today - timedelta(days=29) #
            snapshots = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date >= start_date).order_by(ChannelSnapshot.date.asc()).all() #
            labels = [(start_date + timedelta(days=i)).strftime('%d %b') for i in range(30)] #
            sub_data, view_data, last_subs, last_views = [], [], 0, 0 #
            first_snapshot = ChannelSnapshot.query.filter(ChannelSnapshot.channel_db_id == channel_id, ChannelSnapshot.date < start_date).order_by(ChannelSnapshot.date.desc()).first() #
            if first_snapshot: #
                last_subs, last_views = first_snapshot.subscribers, first_snapshot.views #
            elif snapshots: #
                 last_subs, last_views = snapshots[0].subscribers, snapshots[0].views #
            snapshot_dict = {s.date: s for s in snapshots} #
            for i in range(30): #
                current_date = start_date + timedelta(days=i) #
                if current_date in snapshot_dict: #
                    last_subs, last_views = snapshot_dict[current_date].subscribers, snapshot_dict[current_date].views #
                sub_data.append(last_subs) #
                view_data.append(last_views) #
            growth_chart_data = {'labels': labels, 'subscribers': sub_data, 'views': view_data} #

            videos_data = get_latest_videos(user.channel.channel_id_youtube, max_results=50) #
            all_user_videos = videos_data.get('videos', []) #

            latest_video = all_user_videos[0] if all_user_videos else None #
            if latest_video and len(all_user_videos) > 1: #
                other_videos = all_user_videos[1:10] #
                avg_views = sum(v['view_count'] for v in other_videos) / len(other_videos) if other_videos else 0 #
                performance = round(((latest_video['view_count'] - avg_views) / avg_views) * 100) if avg_views > 0 else 100 #
                latest_video['performance_vs_avg'] = performance #
            elif latest_video: #
                 latest_video['performance_vs_avg'] = 100 #
            top_videos = sorted([v for v in all_user_videos if 'view_count' in v], key=lambda x: x['view_count'], reverse=True)[:3] #

            ai_suggestions = get_ai_video_suggestions(user, user_videos=all_user_videos) #

            final_data_package = { #
                'kpis': kpis, #
                'growth_chart': growth_chart_data, #
                'latest_video': latest_video, #
                'top_videos': top_videos, #
                'ai_suggestions': ai_suggestions #
            } #

            cache_entry = DashboardCache.query.filter_by(user_id=user.id).first() #
            if not cache_entry: #
                cache_entry = DashboardCache(user_id=user.id) #
                db.session.add(cache_entry) #

            cache_entry.data = final_data_package #
            cache_entry.updated_at = datetime.utcnow() #
            db.session.commit() #
            print(f"Successfully updated dashboard for user: {user.email}") #

        except Exception as e: #
            db.session.rollback() #
            tb_str = traceback.format_exc() #
            log_system_event( #
                message=f"Error updating dashboard for user {user.email}", #
                log_type='ERROR', #
                details={'error': str(e), 'traceback': tb_str} #
            ) #

    print("Celery Task: Finished updating all user dashboards.") #


@celery.task
def perform_full_analysis(competitor_id):
    """एक प्रतियोगी के लिए बैकग्राउंड में पूरा डेटा पैकेज लाता है और कैश करता है।"""
    from .routes.api_routes import get_full_competitor_package #
    print(f"Celery Task: Starting full analysis for competitor_id: {competitor_id}") #
    try: #
        get_full_competitor_package(competitor_id, force_refresh=True) #
        print(f"Celery Task: Successfully completed analysis for competitor_id: {competitor_id}") #
    except Exception as e: #
        tb_str = traceback.format_exc() #
        log_system_event( #
            message=f"Celery task failed: Full analysis for competitor_id: {competitor_id}", #
            log_type='ERROR', #
            details={'error': str(e), 'traceback': tb_str} #
        ) #


# --- Thumbnail A/B Testing Celery Jobs ---

TEST_DURATION_HOURS = 24 #

@celery.task(bind=True)
def start_thumbnail_test(self, test_id):
    """A/B टेस्ट शुरू करता है: थंबनेल 'A' सेट करता है और अगले चरण को शेड्यूल करता है।"""
    with current_app.app_context(): #
        test = ThumbnailTest.query.get(test_id) #
        if not test: #
            log_system_event(f"Thumbnail test {test_id} not found.", "ERROR") #
            return #

        user = User.query.get(test.user_id) #
        creds = get_credentials(user) #
        if not creds: #
            test.status = 'error_credentials' #
            db.session.commit() #
            return #

        try: #
            thumb_a_full_path = os.path.join(current_app.static_folder, test.thumbnail_a_path) #
            print(f"Starting A/B test {test_id} for video {test.video_id}. Setting thumbnail A.") #
            set_video_thumbnail(creds, test.video_id, thumb_a_full_path) #

            test.status = 'running_a' #
            test.test_start_time = datetime.utcnow() #
            db.session.commit() #

            duration_seconds = TEST_DURATION_HOURS * 3600 #
            advance_thumbnail_test.apply_async(args=[test_id], countdown=duration_seconds) #
            print(f"Test {test_id} advanced to 'running_a'. Next check scheduled in {TEST_DURATION_HOURS} hours.") #
        except Exception as e: #
            test.status = 'error_start' #
            db.session.commit() #
            log_system_event(f"Error starting thumbnail test {test_id}", "ERROR", {'error': str(e), 'traceback': traceback.format_exc()}) #

@celery.task(bind=True)
def advance_thumbnail_test(self, test_id):
    """थंबनेल 'A' का परिणाम रिकॉर्ड करता है, थंबनेल 'B' सेट करता है, और अंतिम चरण शेड्यूल करता है।"""
    with current_app.app_context(): #
        test = ThumbnailTest.query.get(test_id) #
        if not test or test.status != 'running_a': #
            return #

        user = User.query.get(test.user_id) #
        creds = get_credentials(user) #
        if not creds: #
            test.status = 'error_credentials' #
            db.session.commit() #
            return #

        try: #
            start_date = test.test_start_time.date() #
            end_date = datetime.utcnow().date() #
            ctr_a, error = get_video_ctr(creds, test.video_id, start_date, end_date) #

            if error: #
                raise Exception(error.get('error', 'Unknown analytics error')) #

            test.result_a_ctr = ctr_a #

            thumb_b_full_path = os.path.join(current_app.static_folder, test.thumbnail_b_path) #
            print(f"Recording results for test {test_id} part A. Setting thumbnail B.") #
            set_video_thumbnail(creds, test.video_id, thumb_b_full_path) #

            test.status = 'running_b' #
            test.switch_time = datetime.utcnow() #
            db.session.commit() #

            duration_seconds = TEST_DURATION_HOURS * 3600 #
            finalize_thumbnail_test.apply_async(args=[test_id], countdown=duration_seconds) #
            print(f"Test {test_id} advanced to 'running_b'. Final check in {TEST_DURATION_HOURS} hours.") #
        except Exception as e: #
            test.status = 'error_advance' #
            db.session.commit() #
            log_system_event(f"Error advancing thumbnail test {test_id}", "ERROR", {'error': str(e), 'traceback': traceback.format_exc()}) #

@celery.task(bind=True)
def finalize_thumbnail_test(self, test_id):
    """थंबनेल 'B' का परिणाम रिकॉर्ड करता है, विजेता की घोषणा करता है, और टेस्ट समाप्त करता है।"""
    with current_app.app_context(): #
        test = ThumbnailTest.query.get(test_id) #
        if not test or test.status != 'running_b': #
            return #

        user = User.query.get(test.user_id) #
        creds = get_credentials(user) #
        if not creds: #
            test.status = 'error_credentials' #
            db.session.commit() #
            return #

        try: #
            start_date = test.switch_time.date() #
            end_date = datetime.utcnow().date() #
            ctr_b, error = get_video_ctr(creds, test.video_id, start_date, end_date) #

            if error: #
                raise Exception(error.get('error', 'Unknown analytics error')) #

            test.result_b_ctr = ctr_b #

            thumb_a_full_path = os.path.join(current_app.static_folder, test.thumbnail_a_path) #
            thumb_b_full_path = os.path.join(current_app.static_folder, test.thumbnail_b_path) #

            if test.result_a_ctr is not None and ctr_b is not None and ctr_b > test.result_a_ctr: #
                test.winner = 'b' #
                set_video_thumbnail(creds, test.video_id, thumb_b_full_path) #
            else: #
                test.winner = 'a' if test.result_a_ctr is not None and ctr_b is not None and test.result_a_ctr > ctr_b else 'tie' #
                set_video_thumbnail(creds, test.video_id, thumb_a_full_path) #

            test.status = 'completed' #
            test.test_end_time = datetime.utcnow() #
            db.session.commit() #

            print(f"Test {test_id} finalized. Winner: {test.winner.upper()}") #

            if user.telegram_chat_id: #
                message = f"✅ आपका थंबनेल A/B टेस्ट वीडियो ID `{test.video_id}` के लिए पूरा हो गया है!\n\nविजेता: **थंबनेल {test.winner.upper()}**\n\nCTR A: `{test.result_a_ctr}%`\nCTR B: `{test.result_b_ctr}%`" #
                send_telegram_message(user.telegram_chat_id, message) #

        except Exception as e: #
            test.status = 'error_finalize' #
            db.session.commit() #
            log_system_event(f"Error finalizing thumbnail test {test_id}", "ERROR", {'error': str(e), 'traceback': traceback.format_exc()}) #

@celery.task
def take_video_snapshots():
    """
    सभी प्रतियोगियों के हालिया वीडियो के व्यू काउंट्स को ट्रैक करता है
    ताकि ट्रेंडिंग वीडियो की पहचान की जा सके।
    """
    print("Celery Task: Running job to take video snapshots for trend analysis...") #

    all_competitors = Competitor.query.all() #
    if not all_competitors: #
        print("Celery Task: No competitors to track. Skipping.") #
        return #

    channel_ids_to_check = {comp.channel_id_youtube for comp in all_competitors} #

    new_snapshots = [] #
    for channel_id in channel_ids_to_check: #
        try: #
            videos_data = get_latest_videos(channel_id, max_results=20) #
            if 'error' in videos_data or not videos_data.get('videos'): #
                continue #

            for video in videos_data['videos']: #
                snapshot = VideoSnapshot( #
                    video_id=video['id'], #
                    view_count=video['view_count'] #
                ) #
                new_snapshots.append(snapshot) #
        except Exception as e: #
            log_system_event( #
                message=f"Error fetching videos for snapshot, channel_id: {channel_id}", #
                log_type='ERROR', #
                details={'error': str(e)} #
            ) #
            continue #

    if new_snapshots: #
        try: #
            db.session.bulk_save_objects(new_snapshots) #
            db.session.commit() #
            print(f"Celery Task: Successfully saved {len(new_snapshots)} new video snapshots.") #
        except Exception as e: #
            db.session.rollback() #
            log_system_event( #
                message="Error saving bulk video snapshots to DB", #
                log_type='ERROR', #
                details={'error': str(e), 'traceback': traceback.format_exc()} #
            ) #

    print("Celery Task: Finished taking video snapshots.") #


@celery.task
def bulk_edit_videos(user_id, operations, video_ids):
    """
    Performs bulk editing of YouTube videos in the background with exponential backoff.
    """
    from .models import User #
    user = User.query.get(user_id) #
    if not user: #
        log_system_event("Bulk edit failed: User not found", "ERROR", {'user_id': user_id}) #
        return #

    creds = get_credentials(user) #
    if not creds: #
        log_system_event("Bulk edit failed: Could not get credentials", "ERROR", {'user_id': user_id}) #
        if user.telegram_chat_id: #
            send_telegram_message(user.telegram_chat_id, "❌ Bulk edit failed. Please reconnect your Google account in the dashboard.") #
        return #

    updated_count = 0 #
    failed_count = 0 #

    # Exponential Backoff Parameters #
    MAX_RETRIES = 4 #
    BACKOFF_FACTOR = 2 #

    tags_to_add = [tag.strip() for tag in operations.get('tags_to_add', '').split(',') if tag.strip()] #
    tags_to_remove = {tag.strip().lower() for tag in operations.get('tags_to_remove', '').split(',') if tag.strip()} #
    desc_append = operations.get('description_append', '') #
    new_privacy = operations.get('privacy_status', '') #

    for video_id in video_ids: #
        retries = 0 #
        while retries < MAX_RETRIES: #
            try: #
                # Step 1: Get the latest video data #
                video_data = get_single_video(creds, video_id) #
                if 'error' in video_data: #
                    raise Exception(f"Failed to fetch video data: {video_data['error']}") #

                snippet = video_data['snippet'] #
                status = video_data['status'] #

                # Step 2: Apply the operations #
                current_tags = set(snippet.get('tags', [])) #
                current_tags.update(tags_to_add) #
                final_tags = [tag for tag in current_tags if tag.lower() not in tags_to_remove] #

                new_description = snippet.get('description', '') #
                if desc_append: #
                    new_description += "\n\n" + desc_append #

                final_privacy = new_privacy if new_privacy else status.get('privacyStatus') #

                # Step 3: Update the video #
                update_result = update_video_details( #
                    credentials=creds, #
                    video_id=video_id, #
                    title=snippet.get('title'), #
                    description=new_description, #
                    tags=final_tags, #
                    privacy_status=final_privacy #
                ) #

                if 'error' in update_result: #
                    raise Exception(f"API update error: {update_result['error']}") #
                else: #
                    updated_count += 1 #
                    break #

            except Exception as e: #
                retries += 1 #
                if retries >= MAX_RETRIES: #
                    failed_count += 1 #
                    log_system_event("Bulk edit: Single video update failed after max retries", "ERROR", {'video_id': video_id, 'exception': str(e)}) #
                    break #
                else: #
                    wait_time = BACKOFF_FACTOR * (2 ** (retries - 1)) + random.uniform(0, 1) #
                    log_system_event(f"Bulk edit for video {video_id} failed. Retrying in {wait_time:.2f}s...", "WARNING", {'retry': retries, 'error': str(e)}) #
                    time.sleep(wait_time) #

    if user.telegram_chat_id: #
        message = ( #
            f"✅ *Bulk Edit Complete!*\n\n" #
            f"Successfully updated: *{updated_count} videos*\n" #
            f"Failed to update: *{failed_count} videos*\n\n" #
            f"Please check your YT Manager to see the changes." #
        ) #
        send_telegram_message(user.telegram_chat_id, message) #

# --- बदलाव यहाँ: नया Celery Task जोड़ा गया ---
@celery.task
def cleanup_old_snapshots():
    """Removes API data snapshots older than 30 days."""
    print("Celery Task: Running job to clean up old snapshots...") #
    thirty_days_ago = datetime.utcnow() - timedelta(days=30) #

    try: #
        # Purane Channel Snapshots delete karein #
        deleted_channel_count = ChannelSnapshot.query.filter(ChannelSnapshot.date < thirty_days_ago.date()).delete() #

        # Purane Video Snapshots delete karein #
        deleted_video_count = VideoSnapshot.query.filter(VideoSnapshot.timestamp < thirty_days_ago).delete() #

        db.session.commit() #
        print(f"Celery Task: Cleaned up {deleted_channel_count} old channel snapshots and {deleted_video_count} old video snapshots.") #

    except Exception as e: #
        db.session.rollback() #
        log_system_event( #
            message="Error during old snapshot cleanup", #
            log_type='ERROR', #
            details={'error': str(e), 'traceback': traceback.format_exc()} #
        ) #
    print("Celery Task: Finished cleaning up old snapshots.") #
# --- बदलाव खत्म ---
