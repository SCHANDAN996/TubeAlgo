# tubealgo/services/seo_analyzer.py
"""
SEO Score Analyzer Service
YouTube video aur channel ke liye comprehensive SEO score calculate karta hai
"""

import re
from typing import Dict, List, Tuple
from collections import Counter
import google.generativeai as genai
from tubealgo import db
from tubealgo.models.youtube_models import Video
import logging

logger = logging.getLogger(__name__)


class SEOScoreAnalyzer:
    """
    YouTube SEO Score Calculator
    Video metadata ko analyze karke 0-100 score deta hai
    """
    
    # Power words jo engagement badhate hain
    POWER_WORDS = [
        'amazing', 'incredible', 'ultimate', 'secret', 'proven', 'essential',
        'complete', 'comprehensive', 'master', 'expert', 'professional',
        'exclusive', 'limited', 'shocking', 'revealed', 'exposed', 'truth',
        'mistake', 'avoid', 'warning', 'urgent', 'critical', 'important',
        'free', 'bonus', 'guaranteed', 'easy', 'simple', 'quick', 'fast'
    ]
    
    # Question words
    QUESTION_WORDS = ['how', 'what', 'why', 'when', 'where', 'who', 'which']
    
    def __init__(self, gemini_api_key: str):
        """Initialize SEO Analyzer with Gemini API"""
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
    
    def calculate_video_seo_score(self, video_data: Dict) -> Dict:
        """
        Main method: Complete SEO analysis
        
        Args:
            video_data: Dictionary with video information
                {
                    'title': str,
                    'description': str,
                    'tags': List[str],
                    'duration': int (seconds),
                    'thumbnail': str (url),
                    'view_count': int,
                    'like_count': int,
                    'comment_count': int,
                    'published_at': str,
                    'has_captions': bool
                }
        
        Returns:
            Complete SEO report with score and recommendations
        """
        
        try:
            score = 0
            max_score = 100
            breakdown = {}
            recommendations = []
            
            # 1. Title Analysis (25 points)
            title_score, title_recs = self.analyze_title(
                video_data.get('title', ''),
                video_data.get('tags', [])
            )
            score += title_score
            breakdown['title'] = {'score': title_score, 'max': 25}
            recommendations.extend(title_recs)
            
            # 2. Description Analysis (25 points)
            desc_score, desc_recs = self.analyze_description(
                video_data.get('description', ''),
                video_data.get('tags', [])
            )
            score += desc_score
            breakdown['description'] = {'score': desc_score, 'max': 25}
            recommendations.extend(desc_recs)
            
            # 3. Tags Analysis (15 points)
            tags_score, tags_recs = self.analyze_tags(
                video_data.get('tags', []),
                video_data.get('title', ''),
                video_data.get('description', '')
            )
            score += tags_score
            breakdown['tags'] = {'score': tags_score, 'max': 15}
            recommendations.extend(tags_recs)
            
            # 4. Engagement Analysis (15 points)
            engagement_score, engagement_recs = self.analyze_engagement(
                video_data.get('view_count', 0),
                video_data.get('like_count', 0),
                video_data.get('comment_count', 0)
            )
            score += engagement_score
            breakdown['engagement'] = {'score': engagement_score, 'max': 15}
            recommendations.extend(engagement_recs)
            
            # 5. Video Optimization (10 points)
            optimization_score, opt_recs = self.analyze_video_optimization(
                video_data.get('duration', 0),
                video_data.get('has_captions', False),
                video_data.get('thumbnail', '')
            )
            score += optimization_score
            breakdown['optimization'] = {'score': optimization_score, 'max': 10}
            recommendations.extend(opt_recs)
            
            # 6. Thumbnail Analysis (10 points)
            thumb_score, thumb_recs = self.analyze_thumbnail_presence(
                video_data.get('thumbnail', '')
            )
            score += thumb_score
            breakdown['thumbnail'] = {'score': thumb_score, 'max': 10}
            recommendations.extend(thumb_recs)
            
            # Calculate final grade
            grade = self.get_grade(score)
            grade_color = self.get_grade_color(score)
            
            return {
                'success': True,
                'score': round(score, 1),
                'max_score': max_score,
                'grade': grade,
                'grade_color': grade_color,
                'breakdown': breakdown,
                'recommendations': recommendations,
                'priority_actions': self.get_priority_actions(recommendations),
                'strengths': self.identify_strengths(breakdown),
                'weaknesses': self.identify_weaknesses(breakdown)
            }
            
        except Exception as e:
            logger.error(f"SEO Score calculation error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'score': 0
            }
    
    def analyze_title(self, title: str, tags: List[str]) -> Tuple[float, List[Dict]]:
        """
        Title ko analyze karo (25 points)
        
        Scoring breakdown:
        - Length optimization: 5 points
        - Keyword placement: 5 points  
        - Power words: 5 points
        - Numbers/data: 5 points
        - Clarity & appeal: 5 points
        """
        score = 0.0
        recommendations = []
        
        if not title:
            return 0.0, [{
                'category': 'Title',
                'priority': 'critical',
                'message': 'Title is missing!',
                'impact': 'high'
            }]
        
        title_length = len(title)
        title_lower = title.lower()
        
        # 1. Length Check (5 points)
        if 50 <= title_length <= 70:
            score += 5
        elif 40 <= title_length <= 80:
            score += 3
            recommendations.append({
                'category': 'Title Length',
                'priority': 'medium',
                'message': f'Title length is {title_length} characters. Optimal is 50-70 characters.',
                'impact': 'medium',
                'current': title_length,
                'target': '50-70'
            })
        else:
            score += 1
            recommendations.append({
                'category': 'Title Length',
                'priority': 'high',
                'message': f'Title length is {title_length} characters. Should be 50-70 for best results.',
                'impact': 'high',
                'current': title_length,
                'target': '50-70'
            })
        
        # 2. Keyword Placement (5 points)
        keyword_in_first_half = False
        if tags:
            # Check if any tag appears in first half of title
            mid_point = len(title) // 2
            first_half = title[:mid_point].lower()
            
            for tag in tags[:3]:  # Check top 3 tags
                if tag.lower() in first_half:
                    keyword_in_first_half = True
                    break
            
            if keyword_in_first_half:
                score += 5
            else:
                score += 2
                recommendations.append({
                    'category': 'Keyword Placement',
                    'priority': 'high',
                    'message': 'Place your main keyword in the first half of the title for better SEO.',
                    'impact': 'high',
                    'suggestion': 'Move important keywords to the beginning'
                })
        else:
            score += 2.5
            recommendations.append({
                'category': 'Keywords',
                'priority': 'high',
                'message': 'Add tags to improve SEO analysis accuracy.',
                'impact': 'high'
            })
        
        # 3. Power Words Check (5 points)
        power_words_found = [word for word in self.POWER_WORDS if word in title_lower]
        
        if len(power_words_found) >= 2:
            score += 5
        elif len(power_words_found) == 1:
            score += 3
            recommendations.append({
                'category': 'Title Appeal',
                'priority': 'low',
                'message': f'Add more power words to increase click-through rate. Found: {", ".join(power_words_found)}',
                'impact': 'medium',
                'examples': ['Ultimate', 'Complete', 'Secret', 'Proven']
            })
        else:
            score += 1
            recommendations.append({
                'category': 'Title Appeal',
                'priority': 'medium',
                'message': 'Add power words like "Ultimate", "Complete", "Secret" to make title more engaging.',
                'impact': 'medium',
                'examples': self.POWER_WORDS[:8]
            })
        
        # 4. Numbers/Data (5 points)
        has_numbers = bool(re.search(r'\d+', title))
        has_year = bool(re.search(r'20\d{2}', title))
        
        if has_numbers and has_year:
            score += 5
        elif has_numbers or has_year:
            score += 3
            recommendations.append({
                'category': 'Title Data',
                'priority': 'low',
                'message': 'Consider adding current year (2024/2025) to show content is fresh.',
                'impact': 'low',
                'examples': ['10 Tips for 2025', '5 Best Tools in 2024']
            })
        else:
            score += 1
            recommendations.append({
                'category': 'Title Data',
                'priority': 'medium',
                'message': 'Add numbers or year to improve CTR. E.g., "5 Tips" or "Complete Guide 2025"',
                'impact': 'medium',
                'examples': ['Top 10...', 'Ultimate Guide 2025', '7 Secrets...']
            })
        
        # 5. Clarity & Appeal (5 points)
        # Check for question format
        is_question = any(word in title_lower for word in self.QUESTION_WORDS)
        
        # Check for brackets/parentheses (often used for additional info)
        has_brackets = bool(re.search(r'[\[\(].*[\]\)]', title))
        
        # Check for all caps (bad practice)
        all_caps_words = sum(1 for word in title.split() if word.isupper() and len(word) > 1)
        
        clarity_score = 5
        
        if all_caps_words > 2:
            clarity_score -= 2
            recommendations.append({
                'category': 'Title Formatting',
                'priority': 'medium',
                'message': 'Avoid excessive ALL CAPS words. Use proper capitalization.',
                'impact': 'medium'
            })
        
        if is_question:
            # Questions are good for engagement
            pass
        elif not has_brackets:
            recommendations.append({
                'category': 'Title Structure',
                'priority': 'low',
                'message': 'Consider adding context in brackets, e.g., "How to..." (Complete Guide)',
                'impact': 'low'
            })
        
        score += clarity_score
        
        return score, recommendations
    
    def analyze_description(self, description: str, tags: List[str]) -> Tuple[float, List[Dict]]:
        """
        Description analysis (25 points)
        
        Scoring:
        - Length: 5 points
        - Keyword density: 5 points
        - Links & CTAs: 5 points
        - Timestamps: 5 points
        - Hashtags: 5 points
        """
        score = 0.0
        recommendations = []
        
        if not description:
            return 0.0, [{
                'category': 'Description',
                'priority': 'critical',
                'message': 'Description is missing! This severely impacts SEO.',
                'impact': 'critical'
            }]
        
        desc_length = len(description)
        desc_lower = description.lower()
        
        # 1. Length Check (5 points)
        if desc_length >= 1000:
            score += 5
        elif desc_length >= 500:
            score += 3
            recommendations.append({
                'category': 'Description Length',
                'priority': 'medium',
                'message': f'Description is {desc_length} characters. Aim for 1000+ for best SEO.',
                'impact': 'medium',
                'current': desc_length,
                'target': '1000+'
            })
        elif desc_length >= 250:
            score += 2
            recommendations.append({
                'category': 'Description Length',
                'priority': 'high',
                'message': f'Description is only {desc_length} characters. Write at least 500 characters.',
                'impact': 'high',
                'current': desc_length,
                'target': '500-1000'
            })
        else:
            score += 0.5
            recommendations.append({
                'category': 'Description Length',
                'priority': 'critical',
                'message': f'Description is too short ({desc_length} chars). YouTube recommends 1000+ characters.',
                'impact': 'critical',
                'suggestion': 'Write detailed description with keywords, timestamps, links'
            })
        
        # 2. Keyword Density (5 points)
        keyword_mentions = 0
        if tags:
            for tag in tags[:5]:  # Check top 5 tags
                keyword_mentions += desc_lower.count(tag.lower())
            
            # Optimal: 2-5 mentions of main keyword
            if 2 <= keyword_mentions <= 5:
                score += 5
            elif keyword_mentions > 5:
                score += 3
                recommendations.append({
                    'category': 'Keyword Density',
                    'priority': 'low',
                    'message': f'Keywords mentioned {keyword_mentions} times. Avoid keyword stuffing (aim for 2-5).',
                    'impact': 'low'
                })
            else:
                score += 1
                recommendations.append({
                    'category': 'Keyword Density',
                    'priority': 'high',
                    'message': 'Include your main keywords 2-5 times naturally in description.',
                    'impact': 'high'
                })
        else:
            score += 2
        
        # 3. Links & CTAs (5 points)
        has_links = bool(re.search(r'https?://', description))
        has_subscribe_cta = bool(re.search(r'subscribe|सब्सक्राइब', desc_lower))
        has_social_links = any(platform in desc_lower for platform in ['instagram', 'twitter', 'facebook', 'telegram'])
        
        link_score = 0
        if has_links:
            link_score += 2
        else:
            recommendations.append({
                'category': 'Links',
                'priority': 'medium',
                'message': 'Add relevant links (website, social media, related videos).',
                'impact': 'medium'
            })
        
        if has_subscribe_cta:
            link_score += 2
        else:
            recommendations.append({
                'category': 'Call-to-Action',
                'priority': 'medium',
                'message': 'Add subscribe CTA in description.',
                'impact': 'medium',
                'example': '🔔 Subscribe for more content like this!'
            })
        
        if has_social_links:
            link_score += 1
        
        score += link_score
        
        # 4. Timestamps (5 points)
        # Check for timestamp format like 0:00, 1:23, 10:45
        timestamps = re.findall(r'\d+:\d{2}', description)
        
        if len(timestamps) >= 3:
            score += 5
        elif len(timestamps) >= 1:
            score += 3
            recommendations.append({
                'category': 'Timestamps',
                'priority': 'low',
                'message': f'Add more timestamps (found {len(timestamps)}). Recommend 3+.',
                'impact': 'low'
            })
        else:
            score += 0
            recommendations.append({
                'category': 'Timestamps',
                'priority': 'high',
                'message': 'Add timestamps to improve user experience and engagement.',
                'impact': 'high',
                'example': '0:00 Introduction\n1:23 Main Topic\n5:45 Conclusion'
            })
        
        # 5. Hashtags (5 points)
        hashtags = re.findall(r'#\w+', description)
        
        if 3 <= len(hashtags) <= 15:
            score += 5
        elif 1 <= len(hashtags) < 3:
            score += 3
            recommendations.append({
                'category': 'Hashtags',
                'priority': 'low',
                'message': f'Add more hashtags (found {len(hashtags)}). Optimal is 3-15.',
                'impact': 'low'
            })
        elif len(hashtags) > 15:
            score += 2
            recommendations.append({
                'category': 'Hashtags',
                'priority': 'medium',
                'message': f'Too many hashtags ({len(hashtags)}). YouTube may ignore them. Use 3-15.',
                'impact': 'medium'
            })
        else:
            score += 0
            recommendations.append({
                'category': 'Hashtags',
                'priority': 'medium',
                'message': 'Add 3-15 relevant hashtags to improve discoverability.',
                'impact': 'medium',
                'example': '#YouTubeTips #VideoMarketing #ContentCreation'
            })
        
        return score, recommendations
    
    def analyze_tags(self, tags: List[str], title: str, description: str) -> Tuple[float, List[Dict]]:
        """
        Tags analysis (15 points)
        
        Scoring:
        - Number of tags: 5 points
        - Tag length variety: 3 points
        - Relevance to title: 4 points
        - Common keywords: 3 points
        """
        score = 0.0
        recommendations = []
        
        if not tags:
            return 0.0, [{
                'category': 'Tags',
                'priority': 'critical',
                'message': 'No tags added! Tags are crucial for YouTube SEO.',
                'impact': 'critical',
                'suggestion': 'Add 10-15 relevant tags including long-tail keywords'
            }]
        
        num_tags = len(tags)
        
        # 1. Number of tags (5 points)
        if 10 <= num_tags <= 15:
            score += 5
        elif 5 <= num_tags < 10:
            score += 3
            recommendations.append({
                'category': 'Tag Count',
                'priority': 'medium',
                'message': f'You have {num_tags} tags. Add more (optimal: 10-15).',
                'impact': 'medium',
                'current': num_tags,
                'target': '10-15'
            })
        elif num_tags < 5:
            score += 1
            recommendations.append({
                'category': 'Tag Count',
                'priority': 'high',
                'message': f'Only {num_tags} tags. Add more relevant tags (target: 10-15).',
                'impact': 'high'
            })
        else:
            score += 4
            recommendations.append({
                'category': 'Tag Count',
                'priority': 'low',
                'message': f'{num_tags} tags is good, but keep under 20.',
                'impact': 'low'
            })
        
        # 2. Tag length variety (3 points)
        single_word_tags = sum(1 for tag in tags if len(tag.split()) == 1)
        multi_word_tags = len(tags) - single_word_tags
        
        if single_word_tags > 0 and multi_word_tags > 0:
            score += 3
        elif multi_word_tags == 0:
            score += 1
            recommendations.append({
                'category': 'Tag Variety',
                'priority': 'medium',
                'message': 'Add long-tail keywords (multi-word tags) for better targeting.',
                'impact': 'medium',
                'example': 'Instead of just "cooking", use "easy cooking recipes"'
            })
        else:
            score += 2
        
        # 3. Relevance to title (4 points)
        title_lower = title.lower() if title else ''
        relevant_tags = sum(1 for tag in tags if tag.lower() in title_lower)
        
        relevance_ratio = relevant_tags / num_tags if num_tags > 0 else 0
        
        if relevance_ratio >= 0.3:  # At least 30% tags in title
            score += 4
        elif relevance_ratio >= 0.2:
            score += 2
            recommendations.append({
                'category': 'Tag Relevance',
                'priority': 'medium',
                'message': 'Use more tags that appear in your title for better relevance.',
                'impact': 'medium'
            })
        else:
            score += 1
            recommendations.append({
                'category': 'Tag Relevance',
                'priority': 'high',
                'message': 'Tags should relate to your title. At least 3-4 tags should match title keywords.',
                'impact': 'high'
            })
        
        # 4. Common optimization (3 points)
        # Check for brand tag
        has_brand_tag = any(len(tag) < 15 and tag.istitle() for tag in tags)
        
        # Check for category tags
        common_categories = ['tutorial', 'guide', 'review', 'tips', 'how to', 'hindi', 'english']
        has_category = any(cat in ' '.join(tags).lower() for cat in common_categories)
        
        common_score = 0
        if has_brand_tag:
            common_score += 1.5
        else:
            recommendations.append({
                'category': 'Branding',
                'priority': 'low',
                'message': 'Add your channel name or brand as a tag.',
                'impact': 'low'
            })
        
        if has_category:
            common_score += 1.5
        else:
            recommendations.append({
                'category': 'Category Tags',
                'priority': 'medium',
                'message': 'Add category tags like "tutorial", "guide", "tips", etc.',
                'impact': 'medium'
            })
        
        score += common_score
        
        return score, recommendations
    
    def analyze_engagement(self, views: int, likes: int, comments: int) -> Tuple[float, List[Dict]]:
        """
        Engagement metrics analysis (15 points)
        
        Scoring:
        - Like ratio: 6 points
        - Comment ratio: 5 points
        - Engagement velocity: 4 points
        """
        score = 0.0
        recommendations = []
        
        if views == 0:
            return 0.0, [{
                'category': 'Engagement',
                'priority': 'info',
                'message': 'Video is new or has no views yet.',
                'impact': 'none'
            }]
        
        # 1. Like ratio (6 points)
        like_ratio = (likes / views) * 100 if views > 0 else 0
        
        if like_ratio >= 4:  # Excellent: >4% like rate
            score += 6
        elif like_ratio >= 2:  # Good: 2-4%
            score += 4
            recommendations.append({
                'category': 'Like Rate',
                'priority': 'low',
                'message': f'Like rate is {like_ratio:.2f}%. Aim for 4%+ for excellent engagement.',
                'impact': 'low',
                'current': f'{like_ratio:.2f}%',
                'target': '4%+'
            })
        elif like_ratio >= 1:  # Average: 1-2%
            score += 2
            recommendations.append({
                'category': 'Like Rate',
                'priority': 'medium',
                'message': f'Like rate is {like_ratio:.2f}%. Add CTAs asking viewers to like.',
                'impact': 'medium',
                'suggestion': 'Ask viewers to like in video and description'
            })
        else:  # Poor: <1%
            score += 1
            recommendations.append({
                'category': 'Like Rate',
                'priority': 'high',
                'message': f'Like rate is low ({like_ratio:.2f}%). Engage viewers and ask for likes.',
                'impact': 'high'
            })
        
        # 2. Comment ratio (5 points)
        comment_ratio = (comments / views) * 100 if views > 0 else 0
        
        if comment_ratio >= 0.5:  # Excellent: >0.5%
            score += 5
        elif comment_ratio >= 0.2:  # Good: 0.2-0.5%
            score += 3
            recommendations.append({
                'category': 'Comment Rate',
                'priority': 'low',
                'message': f'Comment rate is {comment_ratio:.2f}%. Encourage more discussion.',
                'impact': 'low'
            })
        else:  # Poor: <0.2%
            score += 1
            recommendations.append({
                'category': 'Comment Rate',
                'priority': 'high',
                'message': f'Low comment rate ({comment_ratio:.2f}%). Ask questions to spark discussion.',
                'impact': 'high',
                'suggestion': 'End video with question, reply to comments, pin comment'
            })
        
        # 3. Overall engagement quality (4 points)
        # Combined metric
        total_engagement = likes + (comments * 2)  # Comments weigh more
        engagement_score = (total_engagement / views) * 100 if views > 0 else 0
        
        if engagement_score >= 5:
            score += 4
        elif engagement_score >= 3:
            score += 2
        else:
            score += 1
            recommendations.append({
                'category': 'Overall Engagement',
                'priority': 'medium',
                'message': 'Improve overall engagement by creating more interactive content.',
                'impact': 'medium',
                'tips': [
                    'Ask viewers questions',
                    'Create polls in community tab',
                    'Reply to comments actively',
                    'Add end screen with related videos'
                ]
            })
        
        return score, recommendations
    
    def analyze_video_optimization(self, duration: int, has_captions: bool, thumbnail: str) -> Tuple[float, List[Dict]]:
        """
        Video technical optimization (10 points)
        
        Scoring:
        - Duration appropriateness: 4 points
        - Captions: 3 points
        - Custom thumbnail: 3 points
        """
        score = 0.0
        recommendations = []
        
        # 1. Duration (4 points)
        duration_minutes = duration / 60 if duration > 0 else 0
        
        if 8 <= duration_minutes <= 15:  # Sweet spot for most content
            score += 4
        elif 5 <= duration_minutes <= 20:  # Acceptable range
            score += 3
        elif duration_minutes > 20:
            score += 2
            recommendations.append({
                'category': 'Video Duration',
                'priority': 'low',
                'message': f'Video is {duration_minutes:.1f} minutes. Consider if all content is necessary.',
                'impact': 'low',
                'suggestion': 'Long videos work well if content is engaging throughout'
            })
        elif duration_minutes < 5:
            score += 2
            recommendations.append({
                'category': 'Video Duration',
                'priority': 'medium',
                'message': f'Video is only {duration_minutes:.1f} minutes. Longer videos (8-15 min) often perform better.',
                'impact': 'medium'
            })
        else:
            score += 1
        
        # 2. Captions (3 points)
        if has_captions:
            score += 3
        else:
            recommendations.append({
                'category': 'Closed Captions',
                'priority': 'high',
                'message': 'Add closed captions to improve accessibility and SEO.',
                'impact': 'high',
                'benefits': [
                    'Better SEO (YouTube indexes caption text)',
                    'Accessible to deaf/hard of hearing',
                    'Non-native speakers can understand better',
                    'Viewers watching without sound'
                ]
            })
        
        # 3. Custom thumbnail (3 points)
        # If thumbnail URL contains certain patterns, it's likely custom
        if thumbnail and ('maxresdefault' in thumbnail or 'hqdefault' in thumbnail):
            # These are auto-generated thumbnails
            recommendations.append({
                'category': 'Custom Thumbnail',
                'priority': 'critical',
                'message': 'Upload a custom thumbnail! Auto-generated thumbnails hurt CTR.',
                'impact': 'critical',
                'tips': [
                    'Use high contrast colors',
                    'Add large, readable text',
                    'Include close-up of faces (if applicable)',
                    'Maintain 1280x720 resolution',
                    'Show emotion or intrigue'
                ]
            })
        elif thumbnail:
            score += 3
        else:
            recommendations.append({
                'category': 'Thumbnail',
                'priority': 'critical',
                'message': 'Thumbnail is missing!',
                'impact': 'critical'
            })
        
        return score, recommendations
    
    def analyze_thumbnail_presence(self, thumbnail: str) -> Tuple[float, List[Dict]]:
        """
        Thumbnail analysis (10 points)
        Detailed analysis would require image processing
        For now, checking if custom thumbnail exists
        """
        score = 0.0
        recommendations = []
        
        if not thumbnail:
            return 0.0, [{
                'category': 'Thumbnail',
                'priority': 'critical',
                'message': 'No thumbnail detected.',
                'impact': 'critical'
            }]
        
        # Check if it's a custom thumbnail (heuristic)
        is_custom = 'maxresdefault' not in thumbnail and 'hqdefault' not in thumbnail
        
        if is_custom:
            score += 10
        else:
            score += 3
            recommendations.append({
                'category': 'Custom Thumbnail',
                'priority': 'critical',
                'message': 'Using auto-generated thumbnail. Create a custom one for 5x better CTR!',
                'impact': 'critical',
                'stats': 'Custom thumbnails can increase CTR by 400-500%',
                'tools': ['Canva', 'Photoshop', 'TubeAlgo Thumbnail Generator']
            })
        
        return score, recommendations
    
    def get_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return 'A+'
        elif score >= 85:
            return 'A'
        elif score >= 80:
            return 'A-'
        elif score >= 75:
            return 'B+'
        elif score >= 70:
            return 'B'
        elif score >= 65:
            return 'B-'
        elif score >= 60:
            return 'C+'
        elif score >= 55:
            return 'C'
        elif score >= 50:
            return 'C-'
        elif score >= 45:
            return 'D'
        else:
            return 'F'
    
    def get_grade_color(self, score: float) -> str:
        """Get color code for grade"""
        if score >= 80:
            return 'green'
        elif score >= 60:
            return 'yellow'
        elif score >= 40:
            return 'orange'
        else:
            return 'red'
    
    def get_priority_actions(self, recommendations: List[Dict]) -> List[Dict]:
        """Filter and return only critical/high priority actions"""
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        
        priority_recs = [r for r in recommendations if r.get('priority') in ['critical', 'high']]
        priority_recs.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 4))
        
        return priority_recs[:5]  # Top 5 priority actions
    
    def identify_strengths(self, breakdown: Dict) -> List[str]:
        """Identify what's working well"""
        strengths = []
        
        for category, data in breakdown.items():
            score = data.get('score', 0)
            max_score = data.get('max', 1)
            percentage = (score / max_score) * 100
            
            if percentage >= 80:
                strengths.append(f"{category.title()}: Excellent ({score}/{max_score})")
        
        return strengths
    
    def identify_weaknesses(self, breakdown: Dict) -> List[str]:
        """Identify areas needing improvement"""
        weaknesses = []
        
        for category, data in breakdown.items():
            score = data.get('score', 0)
            max_score = data.get('max', 1)
            percentage = (score / max_score) * 100
            
            if percentage < 60:
                weaknesses.append(f"{category.title()}: Needs work ({score}/{max_score})")
        
        return weaknesses
    
    def generate_ai_suggestions(self, video_data: Dict, seo_analysis: Dict) -> Dict:
        """
        Use Gemini AI to generate personalized improvement suggestions
        """
        try:
            prompt = f"""
You are a YouTube SEO expert. Analyze this video and provide specific, actionable suggestions.

Video Title: {video_data.get('title', 'N/A')}
Description Length: {len(video_data.get('description', ''))} characters
Tags: {', '.join(video_data.get('tags', [])[:5])}
Current SEO Score: {seo_analysis.get('score', 0)}/100

Based on the weaknesses identified, provide:
1. Three specific title improvements (with examples)
2. Three description optimization tips (with examples)
3. Five recommended tags to add
4. One thumbnail design suggestion

Format as JSON.
"""
            
            response = self.model.generate_content(prompt)
            # Parse response and return structured suggestions
            
            return {
                'ai_suggestions': response.text,
                'generated_at': 'timestamp'
            }
            
        except Exception as e:
            logger.error(f"AI suggestion generation failed: {str(e)}")
            return {'error': 'Could not generate AI suggestions'}


# Helper function for route
def get_video_seo_score(video_id: str, gemini_api_key: str) -> Dict:
    """
    Convenience function to get SEO score for a video
    Used in routes
    """
    analyzer = SEOScoreAnalyzer(gemini_api_key)
    
    # Fetch video data from database
    video = Video.query.filter_by(video_id=video_id).first()
    
    if not video:
        return {'success': False, 'error': 'Video not found'}
    
    video_data = {
        'title': video.title or '',
        'description': video.description or '',
        'tags': video.tags or [],
        'duration': video.duration or 0,
        'thumbnail': video.thumbnail_url or '',
        'view_count': video.view_count or 0,
        'like_count': video.like_count or 0,
        'comment_count': video.comment_count or 0,
        'published_at': video.published_at,
        'has_captions': video.has_captions or False
    }
    
    return analyzer.calculate_video_seo_score(video_data)
