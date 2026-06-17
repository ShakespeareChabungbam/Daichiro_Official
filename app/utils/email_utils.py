"""
Email utility for Daichiro — password reset and invoice emails via Gmail SMTP.
Uses itsdangerous for time-limited signed tokens (30 min expiry).
"""
import smtplib
import html
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app


# ── Token helpers ────────────────────────────────────────────────────────────

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_reset_token(email: str, salt: str = 'password-reset') -> str:
    """Generate a signed, time-limited reset token for the given email."""
    return _serializer().dumps(email, salt=salt)


def verify_reset_token(token: str, salt: str = 'password-reset', max_age: int = 1800):
    """
    Verify a reset token. Returns the email if valid, else raises
    SignatureExpired or BadSignature (both from itsdangerous).
    max_age defaults to 1800 seconds (30 minutes).
    """
    return _serializer().loads(token, salt=salt, max_age=max_age)


# ── Email sending ────────────────────────────────────────────────────────────

def send_reset_email(to_email: str, reset_url: str, name: str = '') -> bool:
    """
    Send a password reset email via Gmail SMTP App Password.
    Returns True on success, False on failure.
    """
    mail_user = os.environ.get('MAIL_USERNAME', '')
    mail_pass = os.environ.get('MAIL_PASSWORD', '')
    mail_from = os.environ.get('MAIL_FROM', mail_user)

    if not mail_user or not mail_pass:
        current_app.logger.error('MAIL_USERNAME / MAIL_PASSWORD not set in .env')
        return False

    subject = 'Reset Your Password \u2014 Daichiro Academy'
    greeting = f'Hi {name},' if name else 'Hi,'

    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 0;">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr>
          <td style="background:#0F2D5E;padding:32px 40px;text-align:center;">
            <h1 style="color:#C9A84C;font-size:22px;margin:0;letter-spacing:1px;">DAICHIRO ACADEMY</h1>
            <p style="color:rgba(255,255,255,0.6);font-size:12px;margin:6px 0 0;letter-spacing:2px;">PROFESSIONAL SKILLS ACADEMY</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 32px;">
            <p style="color:#333;font-size:15px;margin:0 0 12px;">{greeting}</p>
            <p style="color:#555;font-size:14px;line-height:1.7;margin:0 0 24px;">
              We received a request to reset your password.
              Click the button below \u2014 this link is valid for <strong>30 minutes</strong>.
            </p>
            <div style="text-align:center;margin:28px 0;">
              <a href="{reset_url}"
                 style="background:#C9A84C;color:#0F2D5E;font-weight:bold;font-size:14px;
                        text-decoration:none;padding:14px 36px;border-radius:8px;
                        letter-spacing:0.5px;display:inline-block;">
                Reset My Password
              </a>
            </div>
            <p style="color:#999;font-size:12px;line-height:1.6;margin:0;">
              If you didn't request this, ignore this email \u2014 your password won't change.<br>
              Link: <a href="{reset_url}" style="color:#C9A84C;">{reset_url}</a>
            </p>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="background:#f9f9f9;padding:20px 40px;border-top:1px solid #eee;text-align:center;">
            <p style="color:#bbb;font-size:11px;margin:0;">
              &copy; 2025 Daichiro Professional Skills Academy &nbsp;&middot;&nbsp;
              <a href="https://daichiro.in" style="color:#C9A84C;text-decoration:none;">daichiro.in</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    text_body = (
        f"{greeting}\n\n"
        f"Reset your Daichiro Academy password using the link below (valid 30 min):\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, ignore this email.\n\n"
        f"\u2014 Daichiro Academy"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = mail_from
    msg['To'] = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(mail_user, mail_pass)
            server.sendmail(mail_user, to_email, msg.as_string())
        current_app.logger.info(f'Reset email sent to {to_email}')
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send reset email to {to_email}: {e}')
        return False


def send_invoice_email(to_email: str, name: str, package: str,
                       offer_fee: str, original_fee: str,
                       booked_on: str, inv_no: str,
                       subject: str = None,
                       custom_note: str = None) -> bool:
    """
    Send a professional invoice email to a client.
    Returns True on success, False on failure.
    subject: optional override for email subject line.
    custom_note: optional personal message from staff shown at top of email.
    """
    # ── Keep RAW (unescaped) copies — used in plain-text body ────────────────
    raw_name     = (name         or '').strip()
    raw_package  = (package      or '').strip()
    raw_offer    = (offer_fee    or '').strip()
    raw_original = (original_fee or '').strip()
    raw_booked   = (booked_on    or '').strip()
    raw_inv_no   = (inv_no       or '').strip()
    raw_amount   = raw_offer or raw_original

    # ── HTML-escape all values injected into the HTML email body ─────────────
    def _e(s): return html.escape(str(s)) if s else ''
    h_name     = _e(raw_name)
    h_package  = _e(raw_package)
    h_offer    = _e(raw_offer)
    h_original = _e(raw_original)
    h_booked   = _e(raw_booked)
    h_inv_no   = _e(raw_inv_no)

    mail_user = os.environ.get('MAIL_USERNAME', '')
    mail_pass = os.environ.get('MAIL_PASSWORD', '')
    mail_from = os.environ.get('MAIL_FROM', mail_user)

    if not mail_user or not mail_pass:
        current_app.logger.error('MAIL_USERNAME / MAIL_PASSWORD not set in .env')
        return False

    # ── Sanitize subject — strip newlines to prevent email header injection ───
    default_subj = f'Payment Receipt \u2014 Daichiro Academy ({raw_inv_no})'
    if subject:
        subject = subject.replace('\r', '').replace('\n', ' ').strip()
    subject = subject or default_subj

    # ── Build discount row ────────────────────────────────────────────────────
    discount_row = ''
    if raw_offer and raw_original and raw_offer != raw_original:
        try:
            saving = int(raw_original) - int(raw_offer)
            if saving > 0:
                discount_row = f'''
              <tr>
                <td style="padding:8px 14px;color:#16a34a;font-size:13px;">Offer Discount</td>
                <td style="padding:8px 14px;color:#16a34a;font-size:13px;font-weight:700;text-align:right;">\u2212 \u20b9{saving}</td>
              </tr>'''
        except Exception:
            pass

    h_total   = h_offer or h_original or 'As agreed'
    h_regular = h_original or h_total

    # ── Build optional staff note block (HTML) ────────────────────────────────
    note_block = ''
    if custom_note and custom_note.strip():
        note_html = html.escape(custom_note.strip()).replace('\n', '<br>')
        note_block = f'''
        <tr>
          <td style="padding:20px 40px 0;">
            <div style="background:#FFF9E6;border-left:4px solid #C9A84C;border-radius:6px;padding:14px 18px;">
              <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:2px;color:#8B6914;margin-bottom:6px;">Note from Daichiro</div>
              <p style="font-size:13px;color:#555;margin:0;line-height:1.7;">{note_html}</p>
            </div>
          </td>
        </tr>'''

    html_body = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;">
    <tr><td align="center" style="padding:40px 16px;">

      <table width="580" cellpadding="0" cellspacing="0"
             style="max-width:580px;width:100%;background:#ffffff;border-radius:16px;
                    overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,0.12);">

        <!-- ── HEADER ── -->
        <tr>
          <td style="background:#0F2D5E;padding:36px 40px;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td valign="middle">
                <div style="color:#C9A84C;font-size:24px;font-weight:900;letter-spacing:2px;">DAICHIRO</div>
                <div style="color:rgba(255,255,255,0.45);font-size:9px;letter-spacing:3px;margin-top:4px;">PROFESSIONAL SKILLS ACADEMY</div>
              </td>
              <td valign="middle" style="text-align:right;">
                <div style="text-align:center;">
                  <div style="background:rgba(201,168,76,0.15);border:1px solid rgba(201,168,76,0.35);
                              border-radius:10px;padding:10px 18px;display:inline-block;text-align:center;">
                    <div style="color:rgba(255,255,255,0.5);font-size:9px;letter-spacing:2px;text-transform:uppercase;">Receipt</div>
                    <div style="color:#C9A84C;font-size:20px;font-weight:900;margin-top:3px;">{h_inv_no}</div>
                    <div style="color:rgba(255,255,255,0.45);font-size:10px;margin-top:3px;">{h_booked}</div>
                  </div>
                  <div style="margin-top:8px;">
                    <span style="border:2px solid #22c55e;color:#22c55e;font-size:10px;font-weight:900;
                                letter-spacing:3px;text-transform:uppercase;padding:4px 12px;
                                border-radius:6px;display:inline-block;">&#10003; PAID</span>
                  </div>
                </div>
              </td>
            </tr></table>
          </td>
        </tr>

        <!-- ── BILLED TO ── -->
        <tr>
          <td style="background:#071a3e;padding:22px 40px 26px;">
            <div style="color:rgba(255,255,255,0.4);font-size:9px;letter-spacing:3px;text-transform:uppercase;margin-bottom:6px;">Receipt For</div>
            <div style="color:#ffffff;font-size:22px;font-weight:900;letter-spacing:-0.5px;">{h_name}</div>
          </td>
        </tr>

        <!-- ── STAFF NOTE ── -->
        {note_block}

        <!-- ── SERVICE TABLE ── -->
        <tr>
          <td style="padding:32px 40px 0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
              <tr style="background:#f7f8fa;">
                <td style="padding:10px 16px;font-size:10px;font-weight:800;text-transform:uppercase;
                           letter-spacing:2px;color:#999;border-radius:6px 0 0 6px;">
                  Description
                </td>
                <td style="padding:10px 16px;font-size:10px;font-weight:800;text-transform:uppercase;
                           letter-spacing:2px;color:#999;text-align:right;border-radius:0 6px 6px 0;">
                  Amount
                </td>
              </tr>
              <tr>
                <td style="padding:20px 16px;font-size:16px;font-weight:700;color:#1a1a2e;
                           border-bottom:2px solid #e8ecf0;">
                  {h_package}
                </td>
                <td style="padding:20px 16px;font-size:16px;font-weight:900;color:#0F2D5E;
                           text-align:right;border-bottom:2px solid #e8ecf0;">
                  \u20b9{h_offer or h_original}
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── TOTALS ── -->
        <tr>
          <td style="padding:0 40px 36px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {discount_row}

              <tr>
                <td colspan="2" style="padding:10px 0 0;">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="background:#15803d;padding:22px 24px;border-radius:12px 0 0 12px;vertical-align:middle;">
                        <div style="color:#ffffff;font-size:11px;font-weight:900;
                                    text-transform:uppercase;letter-spacing:2px;">&#10003; Amount Paid</div>
                        <div style="color:rgba(255,255,255,0.65);font-size:10px;margin-top:4px;">Payment received &mdash; Thank you!</div>
                      </td>
                      <td style="background:#15803d;padding:22px 24px;text-align:right;border-radius:0 12px 12px 0;vertical-align:middle;">
                        <span style="color:#ffffff;font-size:32px;font-weight:900;letter-spacing:-1px;">\u20b9{h_total}</span>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

            </table>
          </td>
        </tr>

        <!-- ── THANK YOU BANNER ── -->
        <tr>
          <td style="background:#C9A84C;padding:14px 40px;text-align:center;">
            <span style="color:#0F2D5E;font-size:11px;font-weight:900;letter-spacing:3px;text-transform:uppercase;">
              Thank You for Choosing Daichiro &#10084;
            </span>
          </td>
        </tr>

        <!-- ── FOOTER ── -->
        <tr>
          <td style="background:#071a3e;padding:22px 40px;text-align:center;">
            <span style="color:rgba(255,255,255,0.5);font-size:10px;letter-spacing:1px;">
              daichiro.academy@gmail.com
            </span>
            <span style="color:rgba(255,255,255,0.3);font-size:10px;padding:0 8px;">&middot;</span>
            <a href="https://daichiro.in"
               style="color:#C9A84C;font-size:10px;font-weight:700;letter-spacing:1px;text-decoration:none;">
              daichiro.in
            </a>
          </td>
        </tr>

      </table>

    </td></tr>
  </table>
</body>
</html>"""

    # ── Plain-text fallback — uses RAW (unescaped) values ────────────────────
    note_text = f'\nNote from Daichiro:\n{custom_note.strip()}\n' if custom_note and custom_note.strip() else ''
    text_body = (
        f"Hi {raw_name},\n\n"
        f"Your payment has been received. Here is your receipt.\n"
        f"{note_text}\n"
        f"Invoice No : {raw_inv_no}\n"
        f"Service    : {raw_package}\n"
        f"Amount Paid: \u20b9{raw_amount}\n"
        f"Booked On  : {raw_booked}\n\n"

        f"\u2014 Daichiro Professional Skills Academy\n"
        f"  daichiro.academy@gmail.com | daichiro.in"
    )

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = mail_from
    msg['To']      = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(mail_user, mail_pass)
            server.sendmail(mail_user, to_email, msg.as_string())
        current_app.logger.info(f'Invoice email sent to {to_email}')
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send invoice to {to_email}: {e}')
        return False
