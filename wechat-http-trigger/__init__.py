import logging, os, json
import pandas as pd
from smtplib import SMTP_SSL as SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from lxml import etree
import azure.functions as func
from datetime import date
import pymongo
import time

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

def card_pass_handler(xml_tree):
    '''审核通过'''
    card_id = xml_tree.find(".//CardId").text.strip()
    content = f"{card_id} 审核通过，可以使用。"
    send_notification_email("会员卡审核结果", content)

def card_not_pass_handler(xml_tree):
    '''审核未通过'''
    card_id = xml_tree.find(".//CardId").text.strip()
    if xml_tree.find(".//RefuseReason") is not None:
        refuse_reason = xml_tree.find(".//RefuseReason").text.strip()
        content = f"{card_id} 审核未通过，原因：{refuse_reason}。"
    else:
        xml_tree_str = etree.tostring(xml_tree, encoding="utf-8", method="xml")
        content = f"{card_id} 审核未通过，原因未知，{xml_tree_str}。"
    send_notification_email("会员卡审核结果", content)

def generate_all_user_df():
    '''Get all user info from database, convert to csv'''
    mongo_docs = collection.find({})
    df = pd.DataFrame(mongo_docs)
    # mongo's internal id is not needed
    df.pop("_id")
    out_fn = "membership_card.csv"
    csv_content = df.to_csv(index=False)
    return {out_fn: csv_content}

def card_received_by_user(xml_tree):
    '''领取事件推送'''
    # 开发者微信号
    to_username = xml_tree.find(".//ToUserName").text.strip()
    # 领取者openid
    from_username = xml_tree.find(".//FromUserName").text.strip()
    # 消息时间，由于是个从1970-01-01开始的秒数，不如直接用datetime library
    create_time = xml_tree.find(".//CreateTime").text.strip()
    time = date.today().isoformat()
    # 会员卡卡券的unique id
    card_id = xml_tree.find(".//CardId").text.strip()
    # 用户的code序列号
    user_card_code = xml_tree.find(".//UserCardCode").text.strip()
    # 用户删除后找回？可能没什么用
    is_restore = xml_tree.find(".//IsRestoreMemberCard").text.strip()

    # update database
    new_user_dict = {
        "card_id": card_id,
        "open_id": from_username,
        "user_code": user_card_code,
        "received_time": time,
    }
    result = collection.update_one({"open_id": from_username}, {"$set": new_user_dict}, upsert=True)
    logging.info(f"New user created, upserted document with _id {result.upserted_id}\n")

    df_dict = generate_all_user_df()
    send_notification_email("新用户领取会员卡", f"New membership card created: {json.dumps(new_user_dict)}", df_dict)

def card_sku_remind(xml_tree):
    '''库存报警事件，基本用不到'''
    # 开发者微信号
    to_username = xml_tree.find(".//ToUserName").text.strip()
    # 会员卡卡券的unique id
    card_id = xml_tree.find(".//CardId").text.strip()
    # 报警详细信息
    detail = xml_tree.find(".//Detail").text.strip()

    send_notification_email("会员卡库存警告", f"{card_id} 库存警告，{detail}")

def router(event_type, xml_tree):
    if event_type == "card_pass_check":
        card_pass_handler(xml_tree)
    elif event_type == "card_not_pass_check":
        card_not_pass_handler(xml_tree)
    elif event_type == "user_get_card":
        card_received_by_user(xml_tree)
    elif event_type == "card_sku_remind":
        card_sku_remind(xml_tree)

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.method)
    start_time = time.time()
    try:
        body = req.get_body()
        parser = etree.XMLParser(strip_cdata=True)
        tree = etree.fromstring(body, parser)
        msg_type = tree.find(".//MsgType").text.strip()
        assert msg_type == "event", "Message type is not an event."
        event_type = tree.find(".//Event").text.strip()
        router(event_type, tree)
    except Exception as e:
        logging.info(e)
        send_notification_email("Error: Wechat API backend", f"An error occured while processing wechat request: {e}\n Request body: {body}")
        return func.HttpResponse(
            "An error occured while processing wechat request",
            status_code=400
        )
    logging.info(f"Total time elapsed {time.time() - start_time}")
    
    return func.HttpResponse(
        f"This HTTP triggered function executed successfully.\n Request body: {body}",
        status_code=200
    )