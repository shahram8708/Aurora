from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TelField
from wtforms.validators import DataRequired, Email, Length, Regexp, EqualTo, Optional, ValidationError
from app.models import User
from app.extensions import db


class SignupForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = TelField("Phone", validators=[Optional(), Length(min=7, max=20)])
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=50), Regexp(r"^[A-Za-z0-9_.]+$")])
    name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=12),
            Regexp(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).+$", message="Must include upper, lower, number, special."),
        ],
    )
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    accept_terms = BooleanField("I agree to the Terms", validators=[DataRequired()])
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        if db.session.query(User.id).filter_by(email=field.data.lower()).first():
            raise ValidationError("Email already registered")

    def validate_username(self, field):
        if db.session.query(User.id).filter_by(username=field.data.lower()).first():
            raise ValidationError("Username already taken")

    def validate_phone(self, field):
        if field.data and db.session.query(User.id).filter_by(phone=field.data).first():
            raise ValidationError("Phone already in use")


class LoginForm(FlaskForm):
    login = StringField("Email or Username", validators=[DataRequired(), Length(min=3, max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class RequestResetForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField("Send Reset Link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=12),
            Regexp(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).+$", message="Must include upper, lower, number, special."),
        ],
    )
    confirm_password = PasswordField("Confirm", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Reset Password")


class VerifyOTPForm(FlaskForm):
    otp = StringField("Verification Code", validators=[DataRequired(), Regexp(r"^\d{6}$")])
    submit = SubmitField("Verify")


class VerifyEmailForm(FlaskForm):
    token = StringField("Token", validators=[DataRequired()])
    submit = SubmitField("Verify")
