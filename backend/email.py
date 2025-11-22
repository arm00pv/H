import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
from jinja2 import Template

# Mock or Load config from Env
conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "user"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "password"),
    MAIL_FROM = os.getenv("MAIL_FROM", "noreply@datavault.com"),
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = False # For dev
)

# Simple template
VERIFICATION_TEMPLATE = """
<html>
  <body>
    <p>Hi There!</p>
    <p>Please verify your email by clicking this link: <a href="{{ link }}">Verify Email</a></p>
  </body>
</html>
"""

SHARE_TEMPLATE = """
<html>
  <body>
    <p>Hi!</p>
    <p>Someone shared a file with you: <a href="{{ link }}">{{ filename }}</a></p>
  </body>
</html>
"""

class EmailService:
    def __init__(self):
        self.fm = FastMail(conf)

    async def send_verification_email(self, email: EmailStr, token: str):
        # In production, generate a link to the frontend verify page
        link = f"http://localhost:8000/verify-email?token={token}"

        template = Template(VERIFICATION_TEMPLATE)
        html = template.render(link=link)

        message = MessageSchema(
            subject="Verify your DataVault Email",
            recipients=[email],
            body=html,
            subtype="html"
        )

        if os.getenv("MAIL_USERNAME"):
            try:
                await self.fm.send_message(message)
            except Exception as e:
                print(f"Failed to send email: {e}")
        else:
            print(f"MOCK EMAIL to {email}: {link}")

    async def send_share_email(self, to_email: EmailStr, filename: str, link: str):
        template = Template(SHARE_TEMPLATE)
        html = template.render(link=link, filename=filename)

        message = MessageSchema(
            subject=f"File Shared: {filename}",
            recipients=[to_email],
            body=html,
            subtype="html"
        )

        if os.getenv("MAIL_USERNAME"):
            try:
                await self.fm.send_message(message)
            except Exception as e:
                print(f"Failed to send email: {e}")
        else:
            print(f"MOCK SHARE EMAIL to {to_email}: {link}")
