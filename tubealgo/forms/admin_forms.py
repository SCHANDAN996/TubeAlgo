# tubealgo/forms/admin_forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, IntegerField, BooleanField, TextAreaField, DecimalField
from wtforms.validators import DataRequired, Optional, NumberRange, Length
from wtforms.widgets import CheckboxInput

class AdminUserForm(FlaskForm):
    """Form for updating user subscription plans"""
    plan = SelectField(
        'Subscription Plan',
        choices=[
            ('free', 'Free'),
            ('creator', 'Creator'), 
            ('pro', 'Pro')
        ],
        validators=[DataRequired(message="Please select a plan")]
    )
    submit = SubmitField('Update Plan')

class AdminUserEditForm(FlaskForm):
    """Form for editing user details"""
    email = StringField(
        'Email Address',
        validators=[DataRequired(message="Email is required")]
    )
    subscription_plan = SelectField(
        'Subscription Plan',
        choices=[
            ('free', 'Free'),
            ('creator', 'Creator'),
            ('pro', 'Pro')
        ],
        validators=[DataRequired()]
    )
    status = SelectField(
        'Account Status',
        choices=[
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('inactive', 'Inactive')
        ],
        validators=[DataRequired()]
    )
    timezone = StringField('Timezone')
    telegram_chat_id = StringField('Telegram Chat ID')
    submit = SubmitField('Update User')

class SubscriptionPlanForm(FlaskForm):
    """Form for creating/editing subscription plans"""
    plan_id = StringField(
        'Plan ID',
        validators=[DataRequired(), Length(max=50)]
    )
    name = StringField(
        'Plan Name', 
        validators=[DataRequired(), Length(max=100)]
    )
    price = IntegerField(
        'Price (in paise)',
        validators=[DataRequired(), NumberRange(min=0)]
    )
    slashed_price = IntegerField(
        'Slashed Price (in paise)',
        validators=[Optional(), NumberRange(min=0)]
    )
    competitors_limit = IntegerField(
        'Competitors Limit',
        validators=[DataRequired(), NumberRange(min=-1)],
        description="-1 for unlimited"
    )
    keyword_searches_limit = IntegerField(
        'Keyword Searches Limit',
        validators=[DataRequired(), NumberRange(min=-1)],
        description="-1 for unlimited"
    )
    ai_generations_limit = IntegerField(
        'AI Generations Limit',
        validators=[DataRequired(), NumberRange(min=-1)],
        description="-1 for unlimited"
    )
    playlist_suggestions_limit = IntegerField(
        'Playlist Suggestions Limit',
        validators=[DataRequired(), NumberRange(min=-1)],
        description="-1 for unlimited"
    )
    has_discover_tools = BooleanField('Has Discover Tools')
    has_ai_suggestions = BooleanField('Has AI Suggestions')
    has_comment_reply = BooleanField('Has Comment Reply')
    is_popular = BooleanField('Is Popular Plan')
    submit = SubmitField('Save Plan')

class SiteSettingsForm(FlaskForm):
    """Form for site settings"""
    site_name = StringField(
        'Site Name',
        validators=[DataRequired(), Length(max=100)]
    )
    site_announcement = TextAreaField(
        'Site Announcement',
        validators=[Optional(), Length(max=500)],
        description="HTML allowed, displayed at top of pages"
    )
    maintenance_mode = BooleanField('Maintenance Mode')
    google_analytics_id = StringField(
        'Google Analytics ID',
        validators=[Optional(), Length(max=50)]
    )
    contact_email = StringField(
        'Contact Email',
        validators=[Optional(), Length(max=100)]
    )
    submit = SubmitField('Save Settings')

class AISettingsForm(FlaskForm):
    """Form for AI settings"""
    gemini_api_key = StringField(
        'Gemini API Key',
        validators=[Optional(), Length(max=100)],
        description="Leave empty to keep current key"
    )
    openai_api_key = StringField(
        'OpenAI API Key', 
        validators=[Optional(), Length(max=100)],
        description="Leave empty to keep current key"
    )
    ai_model_preference = SelectField(
        'Preferred AI Model',
        choices=[
            ('gemini', 'Google Gemini'),
            ('openai', 'OpenAI GPT')
        ],
        validators=[DataRequired()]
    )
    max_tokens = IntegerField(
        'Max Tokens',
        validators=[DataRequired(), NumberRange(min=100, max=4000)],
        default=1000
    )
    temperature = DecimalField(
        'Temperature',
        validators=[Optional(), NumberRange(min=0, max=1)],
        default=0.7,
        places=2
    )
    submit = SubmitField('Save AI Settings')

class CouponForm(FlaskForm):
    """Form for creating/editing coupons"""
    code = StringField(
        'Coupon Code',
        validators=[DataRequired(), Length(max=50)]
    )
    discount_type = SelectField(
        'Discount Type',
        choices=[
            ('percentage', 'Percentage'),
            ('fixed', 'Fixed Amount')
        ],
        validators=[DataRequired()]
    )
    discount_value = IntegerField(
        'Discount Value',
        validators=[DataRequired(), NumberRange(min=1)]
    )
    max_uses = IntegerField(
        'Maximum Uses',
        validators=[Optional(), NumberRange(min=1)],
        description="Leave empty for unlimited"
    )
    valid_from = StringField('Valid From', validators=[Optional()])
    valid_until = StringField('Valid Until', validators=[Optional()])
    applicable_plans = SelectField(
        'Applicable Plans',
        choices=[
            ('all', 'All Plans'),
            ('creator', 'Creator Plan Only'),
            ('pro', 'Pro Plan Only')
        ],
        validators=[DataRequired()]
    )
    is_active = BooleanField('Is Active', default=True)
    submit = SubmitField('Save Coupon')

class SystemLogFilterForm(FlaskForm):
    """Form for filtering system logs"""
    log_type = SelectField(
        'Log Type',
        choices=[
            ('all', 'All Types'),
            ('INFO', 'Info'),
            ('WARNING', 'Warning'),
            ('ERROR', 'Error'),
            ('QUOTA_EXCEEDED', 'Quota Exceeded')
        ],
        validators=[Optional()]
    )
    date_from = StringField('Date From', validators=[Optional()])
    date_to = StringField('Date To', validators=[Optional()])
    search = StringField('Search Message', validators=[Optional()])
    submit = SubmitField('Filter Logs')

class CacheManagementForm(FlaskForm):
    """Form for cache management actions"""
    action = SelectField(
        'Action',
        choices=[
            ('clear_all', 'Clear All Cache'),
            ('clear_user', 'Clear User Cache'),
            ('clear_competitor', 'Clear Competitor Cache'),
            ('clear_dashboard', 'Clear Dashboard Cache')
        ],
        validators=[DataRequired()]
    )
    user_id = StringField(
        'User ID (for user cache)',
        validators=[Optional()],
        description="Required if clearing user cache"
    )
    submit = SubmitField('Execute Action')

class PaymentSearchForm(FlaskForm):
    """Form for searching payments"""
    search_type = SelectField(
        'Search By',
        choices=[
            ('user_email', 'User Email'),
            ('payment_id', 'Payment ID'),
            ('order_id', 'Order ID')
        ],
        validators=[DataRequired()]
    )
    search_term = StringField(
        'Search Term',
        validators=[DataRequired()]
    )
    date_from = StringField('Date From', validators=[Optional()])
    date_to = StringField('Date To', validators=[Optional()])
    submit = SubmitField('Search Payments')

class BulkUserActionForm(FlaskForm):
    """Form for bulk user actions"""
    action = SelectField(
        'Action',
        choices=[
            ('change_plan', 'Change Subscription Plan'),
            ('suspend', 'Suspend Users'),
            ('activate', 'Activate Users'),
            ('delete', 'Delete Users')
        ],
        validators=[DataRequired()]
    )
    target_plan = SelectField(
        'Target Plan',
        choices=[
            ('free', 'Free'),
            ('creator', 'Creator'),
            ('pro', 'Pro')
        ],
        validators=[Optional()]
    )
    user_ids = TextAreaField(
        'User IDs',
        validators=[DataRequired()],
        description="Enter user IDs separated by commas or new lines"
    )
    confirm_action = BooleanField(
        'I understand this action cannot be undone',
        validators=[DataRequired(message="Please confirm the action")]
    )
    submit = SubmitField('Execute Bulk Action')

class APIKeyForm(FlaskForm):
    """Form for managing API keys"""
    service = SelectField(
        'Service',
        choices=[
            ('youtube', 'YouTube API'),
            ('gemini', 'Google Gemini'),
            ('openai', 'OpenAI'),
            ('telegram', 'Telegram Bot'),
            ('razorpay', 'Razorpay'),
            ('cashfree', 'Cashfree')
        ],
        validators=[DataRequired()]
    )
    api_key = StringField(
        'API Key',
        validators=[DataRequired(), Length(max=200)]
    )
    secret_key = StringField(
        'Secret Key',
        validators=[Optional(), Length(max=200)],
        description="If applicable"
    )
    is_active = BooleanField('Is Active', default=True)
    quota_used = IntegerField(
        'Quota Used',
        validators=[Optional(), NumberRange(min=0)]
    )
    quota_limit = IntegerField(
        'Quota Limit',
        validators=[Optional(), NumberRange(min=0)]
    )
    submit = SubmitField('Save API Key')

class EmailTemplateForm(FlaskForm):
    """Form for email templates"""
    template_name = StringField(
        'Template Name',
        validators=[DataRequired(), Length(max=100)]
    )
    subject = StringField(
        'Email Subject',
        validators=[DataRequired(), Length(max=200)]
    )
    body = TextAreaField(
        'Email Body',
        validators=[DataRequired()],
        description="HTML allowed. Use {{variable}} for dynamic content"
    )
    is_active = BooleanField('Is Active', default=True)
    submit = SubmitField('Save Template')