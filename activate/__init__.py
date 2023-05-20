import logging, json
import azure.functions as func
from datetime import date
import time
import requests
from api_consts import *

def activate_user_card(card_id, user_card_code):
    # 获取access token，时效通常为2小时，剩余时效记录在res["expires_in"]中。
    res = requests.get(f"{wechat_api}/cgi-bin/token?grant_type=client_credential&appid={wechat_app_id}&secret={wechat_app_secret}").json()
    access_token = res["access_token"]

    # 激活会员卡
    card_info_json = {
        "card_id": card_id,
        "code": user_card_code,
        "membership_number": user_card_code,
    }
    res = requests.post(f"{wechat_api}/card/membercard/activate?access_token={access_token}", json=card_info_json).json()

    if res["errcode"] != 0:
        send_notification_email("新用户激活失败", res["errmsg"])
    else:  
        result = collection.update_one({"user_code": user_card_code}, {"$set": {"card_active": True}}, upsert=True)
        logging.info(f"User card status updated, upserted document with _id {result.upserted_id}\n")
        df_dict = generate_all_user_df(filter={})
        send_notification_email("新用户激活成功", f"新用户卡号：{json.dumps(card_info_json, indent=True)}", df_dict)

def handle_post_requests(req: func.HttpRequest):
    try:
        body = req.get_body()
        info = json.loads(body)
        code = info["code"]
        user_doc = collection.find_one({"user_code": code})
        if user_doc is not None:
            card_id = user_doc["card_id"]
            activate_user_card(card_id, code)
            return func.HttpResponse(
                f"This HTTP triggered function executed successfully.\nUser card {code} for {card_id} is activated",
                status_code=200
            )
        else:
            return func.HttpResponse(
                f"This HTTP triggered function executed successfully.\nBut there is no card {code} for {card_id}",
                status_code=200
            )
    except Exception as e:
        return func.HttpResponse(
            f"This HTTP triggered function failed.\nError: {e}",
            status_code=200
        )

def membercard_user_info(req: func.HttpRequest):
    '''
        用户填写、提交资料后，跳转页面时的事件。将会通过req parameters获得会员信息
        Unused: check membercard_user_info in activate.
    '''
    card_id = str(req.params["card_id"])
    encrypt_code = str(req.params["encrypt_code"])
    open_id = str(req.params["openid"])
    activate_ticket = str(req.params["activate_ticket"])
    # safe guard incase of failure
    params_str = json.dumps({
        "card_id": card_id,
        "encrypt_code": encrypt_code,
        "open_id": open_id,
        "activate_ticket": activate_ticket
    }, indent=True)

    # 获取access token，时效通常为2小时，剩余时效记录在res["expires_in"]中。
    res = requests.get(f"{wechat_api}/cgi-bin/token?grant_type=client_credential&appid={wechat_app_id}&secret={wechat_app_secret}").json()
    access_token = res["access_token"]

    # decode encrypted_code
    j = {"encrypt_code": encrypt_code}
    res = requests.post(f"{wechat_api}/card/code/decrypt?access_token={access_token}", json=j).json()
    if res["errcode"] != 0:
        errmsg = res["errmsg"]
        send_notification_email("激活申请：获取用户信息失败", f"原始激活链接信息：{params_str}\n无法解码encrypted_code\nError message: {errmsg}")
        return func.HttpResponse(
            f"激活失败，请稍后重试：\n后台无法获取卡号\nError message: {errmsg}",
            status_code=200
        )
    user_card_code = res["code"]

    # 查询用户填写的资料
    j = {"activate_ticket": activate_ticket}
    res = requests.post(f"{wechat_api}/card/membercard/activatetempinfo/get?access_token={access_token}", json=j).json()
    if res["errcode"] != 0:
        errmsg = res["errmsg"]
        send_notification_email("激活申请：获取用户信息失败", f"原始激活链接信息：{params_str}\n无法获取用户填写的资料\nError message: {errmsg}")
        return func.HttpResponse(
            f"激活失败，请稍后重试：\n后台无法获取用户填写的资料\nError message: {errmsg}",
            status_code=200
        )
    user_info = res["info"]

    receive_time = date.today().isoformat()
    user_info_dict = {
        "card_id": card_id,
        "open_id": open_id,
        "user_code": user_card_code,
        "received_time": receive_time,
        "card_active": False,
    }
    for values in user_info["common_field_list"]:
        if values["name"] == "USER_FORM_INFO_FLAG_NAME":
            user_info_dict["name"] = values["value"]
        if values["name"] == "USER_FORM_INFO_FLAG_EMAIL":
            user_info_dict["email"] = values["value"]
    for values in user_info["custom_field_list"]:
        if values["name"] == "WECHAT_ID":
            user_info_dict["wechat_id"] = values["value"]
    
    result = collection.update_one({"open_id": open_id}, {"$set": user_info_dict}, upsert=True)
    logging.info(f"New user created, upserted document with _id {result.upserted_id}\n")

    for k in user_info_dict:
        user_info_dict[k] = [user_info_dict[k]]
    df = pd.DataFrame(user_info_dict)
    out_fn = "new_member.csv"
    csv_content = df.to_csv(index=False)
    df_dict = {out_fn: csv_content}

    link_agree = f"{activate_api}?activate=1&code={user_card_code}&card_id={card_id}"
    link_disagree = f"{activate_api}?activate=0&code={user_card_code}&card_id={card_id}"
    send_notification_email("新会员审核", f"请阅读{out_fn}，并决定是否同意激活该会员卡。\n同意：\n{link_agree}\n\n不同意：\n{link_disagree}", df_dict)

    return func.HttpResponse(
        f"激活申请发送成功，请等待审核。",
        status_code=200
    )

def handle_get_requests(req: func.HttpRequest):
    if "encrypt_code" in req.params:
        return membercard_user_info(req)
    activate = int(req.params["activate"])
    user_card_code = str(req.params["code"])
    card_id = str(req.params["card_id"])
    if activate == 1:
        activate_user_card(card_id, user_card_code)
        return func.HttpResponse(
            f"This HTTP triggered function executed successfully.\n{user_card_code} 激活成功",
            status_code=200
        )
    else:
        return func.HttpResponse(
            f"This HTTP triggered function executed successfully.\n未激活任何用户。",
            status_code=200
        )

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.method)
    
    if req.method == "POST":
        return handle_post_requests(req)
    elif req.method == "GET":
        return handle_get_requests(req)
