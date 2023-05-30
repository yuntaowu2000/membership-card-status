import logging, json
import azure.functions as func
from datetime import date, timedelta
import requests
from api_consts import *

def renew_user_card(user_doc):
    card_code = user_doc["card_code"]
    activate_date = date.fromisoformat(user_doc["activate_date"])
    deactivate_date = date.fromisoformat(user_doc["deactivate_date"])
    remaining_days = (deactivate_date - date.today()).days 
    if remaining_days > 30:
        msg = {"msg": f"Renew failed. {card_code} 剩余有效期：{remaining_days}天。"}
        reply_body = json.dumps({"err_code": -1, "data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
        return reply_body
    
    # 获取access token，时效通常为2小时，剩余时效记录在res["expires_in"]中。
    res = requests.get(f"{wechat_api}/cgi-bin/token?grant_type=client_credential&appid={wechat_app_id}&secret={wechat_app_secret}").json()
    access_token = res["access_token"]

    # extend by one year
    new_deactivate_date = deactivate_date + timedelta(365)

    card_info_json = {
        "card_id": user_doc["card_id"],
        "code": card_code,
        "membership_number": card_code,
        "activate_begin_time": int((activate_date - date(1970, 1, 1)).total_seconds()),
        "activate_end_time": int((new_deactivate_date - date(1970, 1, 1)).total_seconds()),
    }
    res = requests.post(f"{wechat_api}/card/membercard/activate?access_token={access_token}", json=card_info_json).json()

    if res["errcode"] != 0:
        msg = {"msg": f"""Renew error. {res["errmsg"]}"""}
        reply_body = json.dumps({"err_code": -1, "data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
    else:  
        set_dict = {
            "card_active": True,
            "activate_date": user_doc["activate_date"],
            "deactivate_date": new_deactivate_date.isoformat()
        }
        result = collection.update_one({"card_code": card_code}, {"$set": set_dict}, upsert=True)
        logging.info(f"User card status updated, upserted document with _id {result.upserted_id}\n")
        df_dict = generate_all_user_df(filter={})
        send_notification_email("用户续期成功", f"{card_code} 续期成功，更新后有效期至{new_deactivate_date.isoformat()}。\ncsv文件打开可能存在乱码。日期乱码可以将数据格式从Date改为Short Date。中文乱码在Excel中选择Data-From Text/CSV打开此文件，File Origin（文件格式）选择65001：Unicode(UTF-8)。", df_dict)
        msg = {"msg": f"Card {card_code} is renewed. New deactivation date: {new_deactivate_date.isoformat()}."}
        reply_body = json.dumps({"err_code": 0, "data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
    return reply_body

def handle_post_requests(req: func.HttpRequest):
    try:
        body = req.get_body()
        info = json.loads(body)
        code = info["code"]
        user_doc = collection.find_one({"card_code": code})
        if user_doc is not None and user_doc["card_active"]:
            reply_body = renew_user_card(user_doc)
            return func.HttpResponse(reply_body, status_code=200)
        else:
            msg = {"msg": f"There is no card {code}."}
            reply_body = json.dumps({"err_code": -1, "data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
            return func.HttpResponse(reply_body, status_code=400)
    except Exception as e:
        msg = {"msg": f"Error: {e}"}
        reply_body = json.dumps({"err_code": -1, "data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
        return func.HttpResponse(reply_body, status_code=500)

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.method)
    
    if req.method == "POST":
        return handle_post_requests(req)
