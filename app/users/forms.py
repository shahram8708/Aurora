from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, TextAreaField, FileField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired, Length, Optional, URL, Email


class LinkForm(FlaskForm):
    class Meta:
        csrf = False  # Embedded in parent; avoid per-entry CSRF requirement

    label = StringField("Label", validators=[Optional(), Length(max=50)])
    url = StringField("URL", validators=[Optional(), URL(), Length(max=255)])


class ProfileUpdateForm(FlaskForm):
    class Meta:
        csrf = False  # JWT cookies already protect this view; avoid double CSRF mismatch

    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=50)])
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    bio = TextAreaField("Bio", validators=[Optional(), Length(max=300)])
    profile_photo = FileField("Profile Photo")
    gender = StringField("Gender", validators=[Optional(), Length(max=30)])
    is_private = BooleanField("Private Account")
    is_professional = BooleanField("Professional Account")
    category = StringField("Category", validators=[Optional(), Length(max=80)])
    contact_email = StringField("Contact Email", validators=[Optional(), Email(), Length(max=255)])
    contact_phone = StringField("Contact Phone", validators=[Optional(), Length(max=20)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    links = FieldList(FormField(LinkForm), min_entries=3, max_entries=5)
    submit = SubmitField("Save")


class PrivacyForm(FlaskForm):
    is_private = BooleanField("Private Account")
    submit = SubmitField("Update Privacy")


class ProfessionalForm(FlaskForm):
    is_professional = BooleanField("Professional")
    category = StringField("Category", validators=[Optional(), Length(max=80)])
    submit = SubmitField("Save")
