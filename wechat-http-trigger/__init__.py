import logging, json
import azure.functions as func
from lxml import etree
from datetime import date
import time
import hashlib
import requests
from api_consts import *

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
        "card_code": user_card_code,
        "card_active": False,
        "received_time": time,
    }
    result = collection.update_one({"card_code": user_card_code}, {"$set": new_user_dict}, upsert=True)
    logging.info(f"New user card created, upserted document with _id {result.upserted_id}\n")

def membercard_user_info(xml_tree):
    '''
        用户填写、提交资料后的事件。将会通过card_id和user card code获得会员信息
        Unused: check membercard_user_info in activate.
    '''
    # 会员卡卡券的unique id
    card_id = xml_tree.find(".//CardId").text.strip()
    # 用户的code序列号
    user_card_code = xml_tree.find(".//UserCardCode").text.strip()

    # 获取access token，时效通常为2小时，剩余时效记录在res["expires_in"]中。
    res = requests.get(f"{wechat_api}/cgi-bin/token?grant_type=client_credential&appid={wechat_app_id}&secret={wechat_app_secret}").json()
    access_token = res["access_token"]

    # 获取会员信息
    card_info_json = {
        "card_id": card_id,
        "code": user_card_code
    }
    res = requests.post(f"{wechat_api}/card/membercard/userinfo/get?access_token={access_token}", json=card_info_json).json()
    if res["errcode"] != 0:
        errmsg = res["errmsg"]
        send_notification_email("获取用户信息失败", f"错误消息：{errmsg}\n会员卡对应信息：{json.dumps(card_info_json, indent=True)}")
        return
    
    try:
        receive_time = date.today().isoformat()
        open_id = res["openid"]
        user_info_dict = {
            "card_id": card_id,
            "open_id": open_id,
            "card_code": user_card_code,
            "received_time": receive_time,
            "nickname": res["nickname"],
            "card_status": res["user_card_status"],
            "card_active": False,
        }

        user_info = res["user_info"]
        for values in user_info["common_field_list"]:
            if values["name"] == "USER_FORM_INFO_FLAG_NAME":
                user_info_dict["name"] = values["value"]
            if values["name"] == "USER_FORM_INFO_FLAG_EMAIL":
                user_info_dict["email"] = values["value"]
        for values in user_info["custom_field_list"]:
            if values["name"] == "WECHAT_ID":
                user_info_dict["wechat_id"] = values["value"]
        
        result = collection.update_one({"card_code": user_card_code}, {"$set": user_info_dict}, upsert=True)
        logging.info(f"New user created, upserted document with _id {result.upserted_id}\n")
        
        link_agree = f"{activate_api}?activate=1&code={user_card_code}&card_id={card_id}"
        link_disagree = f"{activate_api}?activate=0&code={user_card_code}&card_id={card_id}"
        send_notification_email("新会员审核", f"{json.dumps(user_info_dict)}\n请阅读以上内容，并决定是否同意激活该会员卡。\n同意：\n{link_agree}\n\n不同意：\n{link_disagree}")
    except Exception as e:
        send_notification_email("获取用户信息失败", f"Error: {e}\nData: {json.dumps(res, indent=True)}")

def card_sku_remind(xml_tree):
    '''库存报警事件，基本用不到'''
    # 开发者微信号
    to_username = xml_tree.find(".//ToUserName").text.strip()
    # 会员卡卡券的unique id
    card_id = xml_tree.find(".//CardId").text.strip()
    # 报警详细信息
    detail = xml_tree.find(".//Detail").text.strip()

    send_notification_email("会员卡库存警告", f"{card_id} 库存警告，{detail}")

def post_request_router(event_type, xml_tree):
    if event_type == "card_pass_check":
        card_pass_handler(xml_tree)
    elif event_type == "card_not_pass_check":
        card_not_pass_handler(xml_tree)
    elif event_type == "user_get_card":
        card_received_by_user(xml_tree)
    elif event_type == "card_sku_remind":
        card_sku_remind(xml_tree)
    elif event_type == "submit_membercard_user_info":
        membercard_user_info(xml_tree)

def handle_post_requests(req: func.HttpRequest):
    start_time = time.time()
    try:
        body = req.get_body()
        parser = etree.XMLParser(strip_cdata=True)
        tree = etree.fromstring(body, parser)
        msg_type = tree.find(".//MsgType").text.strip()
        assert msg_type == "event", "Message type is not an event."
        event_type = tree.find(".//Event").text.strip()
        post_request_router(event_type, tree)
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

def handle_get_requests(req: func.HttpRequest):
    '''for initial signature check'''
    signature = str(req.params["signature"])
    timestamp = str(req.params["timestamp"])
    nonce = str(req.params["nonce"])
    echostr = str(req.params["echostr"])

    # 将token、timestamp、nonce三个参数进行字典序排序
    token = "UTCGA" # we define this
    arr = [token, timestamp, nonce]
    arr.sort()
    # 将三个参数字符串拼接成一个字符串进行sha1加密
    tmp_str = "".join(arr)
    sha1 = hashlib.sha1()
    sha1.update(tmp_str.encode("utf-8"))
    tmp_str = sha1.hexdigest()
    # 开发者获得加密后的字符串可与signature对比，标识该请求来源于微信

    if tmp_str == signature:
        send_notification_email("微信接入验证成功", json.dumps({
            "signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "echostr": echostr,
        }, indent=True))
        return func.HttpResponse(
            echostr,
            status_code=200
        )
    else:
        # 验证失败
        send_notification_email("微信接入验证失败", json.dumps({
            "signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "echostr": echostr,
        }, indent=True))
        return func.HttpResponse(
            "",
            status_code=500
        )

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info(req.method)
    
    if req.method == "POST":
        return handle_post_requests(req)
    elif req.method == "GET":
        return handle_get_requests(req)