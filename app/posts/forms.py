from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, FloatField, SubmitField, MultipleFileField, SelectField
from wtforms.validators import DataRequired, Length, Optional


class PostCreateForm(FlaskForm):
    caption = TextAreaField("Caption", validators=[Optional(), Length(max=2200)])
    location_name = StringField("Location", validators=[Optional(), Length(max=255)])
    location_latitude = FloatField("Latitude", validators=[Optional()])
    location_longitude = FloatField("Longitude", validators=[Optional()])
    branded_content_tag = StringField("Branded Partner", validators=[Optional(), Length(max=255)])
    hide_like_count = BooleanField("Hide like count")
    media = MultipleFileField("Media", validators=[DataRequired()])
    brightness = FloatField("Brightness", default=1.0, validators=[Optional()])
    contrast = FloatField("Contrast", default=1.0, validators=[Optional()])
    crop_x = FloatField("Crop X", validators=[Optional()])
    crop_y = FloatField("Crop Y", validators=[Optional()])
    crop_width = FloatField("Crop Width", validators=[Optional()])
    crop_height = FloatField("Crop Height", validators=[Optional()])
    image_filter = SelectField(
        "Filter",
        choices=[("none", "None"), ("blur", "Blur"), ("sharpen", "Sharpen"), ("grayscale", "Grayscale")],
        default="none",
    )
    submit = SubmitField("Share")


class PostEditForm(FlaskForm):
    caption = TextAreaField("Caption", validators=[Optional(), Length(max=2200)])
    location_name = StringField("Location", validators=[Optional(), Length(max=255)])
    location_latitude = FloatField("Latitude", validators=[Optional()])
    location_longitude = FloatField("Longitude", validators=[Optional()])
    branded_content_tag = StringField("Branded Partner", validators=[Optional(), Length(max=255)])
    hide_like_count = BooleanField("Hide like count")
    submit = SubmitField("Update")
