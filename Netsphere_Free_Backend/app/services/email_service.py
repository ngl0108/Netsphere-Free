import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
from app.models.settings import SystemSetting

class EmailService:
    @staticmethod
    def get_setting_value(db: Session, key: str, default: str = "") -> str:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting else default

    @staticmethod
    def send_email(db: Session, to_email: str, subject: str, content: str) -> dict:
        # Load SMTP Config
        host = EmailService.get_setting_value(db, "smtp_host", "smtp.gmail.com")
        port = int(EmailService.get_setting_value(db, "smtp_port", "587"))
        username = EmailService.get_setting_value(db, "smtp_user", "")
        password = EmailService.get_setting_value(db, "smtp_password", "")
        from_email = EmailService.get_setting_value(db, "smtp_from", username)

        # [NEW] to_email이 None이면 관리자 이메일(contact_email) 사용
        if not to_email:
            to_email = EmailService.get_setting_value(db, "contact_email", "")
        
        if not to_email:
            return {"success": False, "error": "No recipient email configured."}

        if not username or not password:
            return {"success": False, "error": "SMTP credentials not configured."}

        try:
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(content, 'plain'))

            server = smtplib.SMTP(host, port)
            server.starttls()
            server.login(username, password)
            text = msg.as_string()
            server.sendmail(from_email, to_email, text)
            server.quit()
            
            return {"success": True, "message": "Email sent successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}
