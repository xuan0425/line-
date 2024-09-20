import sys
from gevent import monkey
monkey.patch_all()  # 確保早期進行monkey patching

sys.setrecursionlimit(2000)  # 根據需要調整這個值

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# Line Bot API 和 Handler
line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')

GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  # 預設群組 ID

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')  # 使用 .get() 防止 header 缺失導致的 KeyError
    body = request.get_data(as_text=True)

    print(f"Received request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature error")
        abort(400)
    except Exception as e:
        print(f"Error in callback: {e}")
        abort(500)

    return 'OK'

# 處理接收到的文本消息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text

    print(f"Received message: {user_message}")

    # 檢查是否是/設定群組指令
    if user_message.startswith('/設定群組'):
        if event.source.type == 'group':
            GROUP_ID = event.source.group_id  # 更新群組ID
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"群組ID已更新為：{GROUP_ID}")
            )
            print(f"Group ID updated to: {GROUP_ID}")
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此指令只能在群組中使用。")
            )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000, debug=True)  # 確保 Flask 在 Render 平台上正常運行
