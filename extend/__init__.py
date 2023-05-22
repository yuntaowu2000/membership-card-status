import logging, json
import azure.functions as func
from datetime import date, timedelta
import requests
from api_consts import *

def extend_user_card(user_doc):
    # 获取access token，时效通常为2小时，剩余时效记录在res["expires_in"]中。
    res = requests.get(f"{wechat_api}/cgi-bin/token?grant_type=client_credential&appid={wechat_app_id}&secret={wechat_app_secret}").json()
    access_token = res["access_token"]

    # extend by one year
    activate_date = date.fromisoformat(user_doc["activate_date"])
    deactivate_date = date.fromisoformat(user_doc["deactivate_date"])
    new_deactivate_date = deactivate_date + timedelta(365)

    card_code = user_doc["card_code"]

    card_info_json = {
        "card_id": user_doc["card_id"],
        "code": card_code,
        "membership_number": card_code,
        "activate_begin_time": int((activate_date - date(1970, 1, 1)).total_seconds()),
        "activate_end_time": int((new_deactivate_date - date(1970, 1, 1)).total_seconds()),
    }
    res = requests.post(f"{wechat_api}/card/membercard/activate?access_token={access_token}", json=card_info_json).json()

    if res["errcode"] != 0:
        msg = {"msg": f"""{card_code} 续期失败。{res["errmsg"]}"""}
        reply_body = json.dumps({"data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
    else:  
        set_dict = {
            "card_active": True,
            "activate_date": user_doc["activate_date"],
            "deactivate_date": new_deactivate_date.isoformat()
        }
        result = collection.update_one({"card_code": card_code}, {"$set": set_dict}, upsert=True)
        logging.info(f"User card status updated, upserted document with _id {result.upserted_id}\n")
        df_dict = generate_all_user_df(filter={})
        send_notification_email("用户续期成功", f"{card_code} 续期成功，更新后有效期至{new_deactivate_date.isoformat()}。csv文件包含全会员卡数据。", df_dict)
        msg = {"msg": f"{card_code} 续期成功，更新后有效期至{new_deactivate_date.isoformat()}。"}
        reply_body = json.dumps({"data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
    return reply_body

def handle_post_requests(req: func.HttpRequest):
    try:
        body = req.get_body()
        info = json.loads(body)
        code = info["code"]
        user_doc = collection.find_one({"card_code": code})
        if user_doc is not None and user_doc["card_active"]:
            reply_body = extend_user_card(user_doc)
            return func.HttpResponse(json.dumps(json.loads(reply_body)), status_code=200)
        else:
            msg = {"msg": f"This HTTP triggered function executed successfully.\nBut there is no user card {code}."}
            reply_body = json.dumps({"data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
            return func.HttpResponse(json.dumps(json.loads(reply_body)), status_code=400)
    except Exception as e:
        msg = {"msg": f"This HTTP triggered function failed.\nError: {e}"}
        reply_body = json.dumps({"data_list": [eval(json.dumps(msg, ensure_ascii=False, separators=(",",":")))]}, ensure_ascii=False, separators=(",",":"))
        return func.HttpResponse(json.dumps(json.loads(reply_body)), status_code=500)

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.method)
    
    if req.method == "POST":
        return handle_post_requests(req)
