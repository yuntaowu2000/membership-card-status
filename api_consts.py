import logging, json, os
from smtplib import SMTP_SSL as SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import pymongo
import pandas as pd

# make sure the required data are properly set up, because the errors here won't be notified through email
with open(".jsonfiles/email.json", "r") as f:
    email_data = json.loads(f.read())
try:
    server = SMTP(email_data["server"], 587)
except:
    server = SMTP(email_data["server"], 465)
server.login(email_data["user"], email_data["key"])

dev_email_json = ".jsonfiles/email_dev.json"
if not os.path.exists(dev_email_json):
    dev_email_json = ".jsonfiles/email.json"
    logging.info("dev email json doesn't exist, using previous email json instead")

with open(dev_email_json, "r") as f:
    email_dev_data = json.loads(f.read())
try:
    server_dev = SMTP(email_dev_data["server"], 587)
except:
    server_dev = SMTP(email_dev_data["server"], 465)
server_dev.login(email_dev_data["user"], email_dev_data["key"])

with open(".jsonfiles/database.json", "r") as f:
    db_data = json.loads(f.read())
db_name = db_data["db_name"]
collection_name = db_data["collection_name"]
client = pymongo.MongoClient(db_data["cosmos_conn_str"])
collection = client[db_name][collection_name]

with open(".jsonfiles/wechat.json", "r") as f:
    wechat_data = json.loads(f.read())
wechat_app_id = wechat_data["app_id"]
wechat_app_secret = wechat_data["app_secret"]

with open(".jsonfiles/base_urls.json", "r") as f:
    base_urls = json.loads(f.read())
wechat_api = base_urls["wechat_api"]
activate_api = base_urls["activate_api"]

def send_notification_email(subject, content, files: dict={}, to=None, server=server):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = email_data["user"]
    msg.attach(MIMEText(content, "plain", "utf-8"))

    for f in files:
        part = MIMEText(files[f], "base64", "utf-8")
        part["Content-Type"] = "application/octet-stream"
        part["Content-Disposition"] = f"""attachment; filename="{f}" """
        msg.attach(part)

    server.sendmail(email_data["user"], email_data["to"] if to is None else to, msg.as_string())
    logging.info(f"Email sent: {content}")

def generate_all_user_df(filter={}):
    '''Get all user info from database, convert to xlsx for proper handling of special characters'''
    mongo_docs = collection.find(filter)
    df = pd.DataFrame(mongo_docs)
    # mongo's internal id is not needed
    df.pop("_id")
    df = df[["name", "email", "wechat_id", "wechat_nickname", "program", 
                  "card_id", "open_id", "card_code", "card_active",
                  "received_date", "submission_date", "activate_date", "deactivate_date"]]
    df = df.dropna(subset=["name"])
    df = df.sort_values(by="name")
    out_fn = "membership_card.csv"
    content = df.to_csv(index=False)
    return {out_fn: content}