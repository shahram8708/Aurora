from flask_wtf import FlaskForm
from wtforms import SelectField, FileField, TextAreaField, BooleanField, StringField, IntegerField
from wtforms.validators import DataRequired, Optional, Length


class StoryCreateForm(FlaskForm):
    story_type = SelectField(
        "Type",
        choices=[("photo", "Photo"), ("video", "Video"), ("text", "Text-only")],
        validators=[DataRequired()],
    )
    media = FileField("Media", validators=[Optional()])
    text_content = TextAreaField("Text", validators=[Optional(), Length(max=800)])
    is_close_friends = BooleanField("Close friends", default=False)
    stickers = TextAreaField("Stickers JSON", validators=[Optional()])
    drawing_json = TextAreaField("Drawing JSON", validators=[Optional()])
    link_url = StringField("Link", validators=[Optional(), Length(max=255)])
    music_id = IntegerField("Music", validators=[Optional()])
