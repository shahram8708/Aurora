from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, FloatField, DateTimeField, FileField, IntegerField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class ReelUploadForm(FlaskForm):
    caption = TextAreaField("Caption", validators=[Optional(), Length(max=2200)])
    video = FileField("Video", validators=[DataRequired()])
    music_id = IntegerField("Music", validators=[Optional()])
    speed_factor = FloatField("Speed", validators=[Optional(), NumberRange(min=0.1, max=3.0)])
    allow_download = BooleanField("Allow download", default=True)
    monetization_enabled = BooleanField("Enable monetization", default=False)
    scheduled_at = DateTimeField("Schedule", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    text_overlays = TextAreaField("Text overlays JSON", validators=[Optional()])
    effects_metadata = TextAreaField("Effects JSON", validators=[Optional()])
    stickers_metadata = TextAreaField("Stickers JSON", validators=[Optional()])
    is_remix = BooleanField("Remix", default=False)
    original_reel_id = StringField("Original Reel", validators=[Optional()])
    voiceover = FileField("Voiceover", validators=[Optional()])
    mix_ratio = FloatField("Mix Ratio", validators=[Optional(), NumberRange(min=0.0, max=1.0)])
    background_image = FileField("Green Screen Background", validators=[Optional()])
    green_screen_subject_mask = BooleanField("Subject mask provided", default=False)
    countdown_seconds = IntegerField("Countdown", validators=[Optional(), NumberRange(min=0, max=10)])
    countdown_autostart = BooleanField("Auto start", default=False)
    filter_id = IntegerField("AR Filter", validators=[Optional()])
