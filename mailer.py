"""Single place for outgoing email config and sending. Used to be five
separate copies of the same .env-loading loop and SMTP login/send block
spread across auth.py, notify.py, weekview.py, backup.py and quotepdf.py -
now there's one place to change if the mail provider or credentials ever
change again.

Sends via the Microsoft Graph API (OAuth2 client-credentials flow)
rather than SMTP, since the Microsoft 365 tenant has legacy SMTP AUTH
switched off org-wide with no per-app exception. The app registration's
Mail.Send permission is scoped by an Exchange Online application access
policy to just the one mailbox (see MAIL_FROM), set up by the IT
provider.
"""
import os, base64, requests

for _env in ("/home/SalesChorleyConcrete/laying/.env",
             "/home/SalesChorleyConcrete/GenieAgg/.env"):
    if os.path.exists(_env):
        for _l in open(_env):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

MS_TENANT_ID = os.environ.get("MS_TENANT_ID")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
# The mailbox everything is sent as/through - both the Graph "send as this
# user" endpoint and the visible From address.
MAIL_FROM = os.environ.get("MAIL_FROM")


def _check(r, what):
    if not r.ok:
        raise RuntimeError("%s failed (%s): %s" % (what, r.status_code, r.text[:500]))


def _access_token():
    url = "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % MS_TENANT_ID
    r = requests.post(url, data={
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }, timeout=20)
    _check(r, "Getting a Graph API token")
    return r.json()["access_token"]


def _graph_payload(m):
    """Translates an email.message.EmailMessage (built the same way it
    always was - set_content()/add_alternative()/add_attachment()) into
    the JSON body the Graph API's sendMail endpoint expects."""
    body_part = m.get_body(("html", "plain"))
    content_type = "HTML" if body_part.get_content_type() == "text/html" else "Text"
    to_field = m["To"] or ""
    recipients = [{"emailAddress": {"address": addr.strip()}}
                  for addr in to_field.split(",") if addr.strip()]
    message = {
        "subject": m["Subject"] or "",
        "body": {"contentType": content_type, "content": body_part.get_content()},
        "toRecipients": recipients,
    }
    attachments = []
    for part in m.iter_attachments():
        data = part.get_content()
        if isinstance(data, str):
            data = data.encode()
        attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": part.get_filename() or "attachment",
            "contentType": part.get_content_type(),
            "contentBytes": base64.b64encode(data).decode(),
        })
    if attachments:
        message["attachments"] = attachments
    return {"message": message, "saveToSentItems": "true"}


def send(m):
    """Sends an already-built email.message.EmailMessage via Graph."""
    if not m.get("From"):
        m["From"] = MAIL_FROM
    token = _access_token()
    url = "https://graph.microsoft.com/v1.0/users/%s/sendMail" % MAIL_FROM
    r = requests.post(url, headers={"Authorization": "Bearer " + token},
                      json=_graph_payload(m), timeout=30)
    _check(r, "Sending mail via Graph")
