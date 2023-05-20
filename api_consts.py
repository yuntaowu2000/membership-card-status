import logging, json
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

def send_notification_email(subject, content, files: dict={}):
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = email_data["user"]
    msg.attach(MIMEText(content, "plain"))

    for f in files:
        part = MIMEApplication(files[f], Name=f)
        part["Content-Disposition"] = f"""attachment; filename="{f}" """
        msg.attach(part)

    server.sendmail(email_data["user"], email_data["to"], msg.as_string())
    logging.info(f"Email sent: {content}")

def generate_all_user_df(filter={}):
    '''Get all user info from database, convert to csv'''
    mongo_docs = collection.find(filter)
    df = pd.DataFrame(mongo_docs)
    # mongo's internal id is not needed
    df.pop("_id")
    out_fn = "membership_card.csv"
    csv_content = df.to_csv(index=False)
    return {out_fn: csv_content}