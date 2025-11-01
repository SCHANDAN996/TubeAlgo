# tubealgo/forms/youtube_forms.py

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, SubmitField, SelectField, TextAreaField, DateTimeLocalField
from wtforms.validators import DataRequired, Length, Optional

class PlaylistForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=5000)])
    privacy_status = SelectField(
        'Visibility', 
        choices=[('public', 'Public'), ('unlisted', 'Unlisted'), ('private', 'Private')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Playlist')

class VideoForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=5000)])
    tags = StringField('Tags', validators=[Optional(), Length(max=500)])
    thumbnail = FileField('Thumbnail', validators=[Optional(), FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')])
    visibility = SelectField(
        'Visibility', 
        choices=[
            ('private', 'Private'), 
            ('unlisted', 'Unlisted'), 
            ('public', 'Public'),
            ('schedule', 'Schedule / Premiere')
        ], 
        validators=[DataRequired()]
    )
    publish_at = DateTimeLocalField('Premiere / Schedule At', format='%Y-%m-%dT%H:%M:%S', validators=[Optional()])
    submit = SubmitField('Save Changes')

class UploadForm(VideoForm):
    video_file = FileField('Video File', 
        validators=[
            FileRequired(), 
            FileAllowed(['mp4', 'mov', 'webm', 'mkv', 'avi'], 'Only video files are allowed!')
        ],
        render_kw={'accept': 'video/*'}
    )
    submit = SubmitField('Upload Video')