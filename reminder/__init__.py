from datetime import date
import azure.functions as func
from api_consts import *
import pandas as pd
from pymongo import UpdateOne

def main(mytimer: func.TimerRequest) -> None:
    '''
        Automatically deactivate any card that has days_to_deactivate <= 0. 
        Send reminders to card that has 0<days_to_deactivate<=21.
    '''
    result = collection.find({})
    df = pd.DataFrame(result)
    df = df.dropna()
    df["days_to_deactivate"] = df["deactivate_date"].apply(lambda x: (date.fromisoformat(str(x))- date.today()).days)

    df_to_deactivate = df[(df["days_to_deactivate"] <= 0) & (df["card_active"] == True)]
    if len(df_to_deactivate) > 0:
        updates = []
        for code in df_to_deactivate["card_code"].values:
            updates.append(UpdateOne({"card_code": code}, {'$set': {"card_active": False}}))
        result = collection.bulk_write(updates)
        logging.info(f"Deactivated {result.modified_count} cards")

    df_to_remind = df[(df["days_to_deactivate"] > 0) & (df["days_to_deactivate"] <= 21)]
    for i in range(len(df_to_remind)):
        user_name = df_to_remind["name"].values[i]
        user_code = int(df_to_remind["card_code"].values[i])
        user_email = df_to_remind["email"].values[i]
        deactive_date = str(df_to_remind["deactivate_date"].values[i])
        days_to_deactivate = df_to_remind["days_to_deactivate"].values[i]
        # use 0 to prepend the user code in case of 0 leading card code being truncated by pandas.
        send_notification_email("UTCGA会员续费提醒", f"{user_name} 您好。\n您的会员卡：{user_code:0>12} 将于{deactive_date}（{days_to_deactivate}天后）过期。请及时续费，以免会员卡失效（需重新开卡）。\nSincerely,\nUTCGA", to=user_email)
