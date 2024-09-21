import sys
from gevent import monkey
monkey.patch_all()

sys.setrecursionlimit(2000)
from flask import Flask, request, abort, jsonify
from flask_socketio import SocketIO
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate,
    PostbackAction, ImageMessage, ImageSendMessage, PostbackEvent
)
from linebot.exceptions import InvalidSignatureError, LineBotApiError  # 添加 LineBotApiError
import concurrent.futures
import requests
import json
import time
import os


app = Flask(__name__)
socketio = SocketIO(app, async_mode=None)

line_bot_api = LineBotApi(os.getenv('LINE_BOT_API'))  # 使用環境變數
handler = WebhookHandler(os.getenv('LINE_HANDLER'))
GROUP_ID = ('C3dca1e6da36d110cdfc734c47180e428')

pending_texts = {}
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# API 使用狀況
api_usage_count = 0

# 紀錄 API 請求次數
def track_api_usage():
    global api_usage_count
    api_usage_count += 1
    print(f"API requests count: {api_usage_count}")

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
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

@app.route('/api_usage', methods=['GET'])
def get_api_usage():
    return jsonify({"api_usage_count": api_usage_count})

@app.route('/')
def index():
    return "Hello, World!"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text
    user_id = event.source.user_id
    source_type = event.source.type

    print(f"Received message: {user_message} from {source_type}")

    if source_type == 'group':
        if user_message.startswith('/設定群組'):
            GROUP_ID = event.source.group_id
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"群組ID已更新為：{GROUP_ID}")
            )
            print(f"Group ID updated to: {GROUP_ID}")
        else:
            print("Ignoring non-/設定群組 message in group.")
            return

    if source_type == 'user':
        if user_id in pending_texts:
            action = pending_texts[user_id].get('action')
            if action == 'add_text':
                text_message = user_message
                image_url = pending_texts[user_id].get('image_url')

                if image_url:
                    executor.submit(upload_and_send_image, image_url, user_id, text_message)
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text='文字已成功添加。')
                    )
                else:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text='找不到圖片，請重新上傳。')
                    )
            elif user_message.lower() == '取消':
                del pending_texts[user_id]
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='操作已取消。')
                )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    source_type = event.source.type

    if source_type == 'user':
        reset_pending_state(user_id)

        message_id = event.message.id
        image_content = line_bot_api.get_message_content(message_id)

        try:
            image_url = upload_image_to_postimage(image_content)

            if image_url:
                print(f'Image successfully uploaded to {image_url}')
                pending_texts[user_id] = {'action': 'add_text', 'image_url': image_url}
            else:
                raise Exception("Image upload failed")

        except Exception as e:
            print(f'Error processing image: {e}')
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='圖片上傳失敗，請稍後再試。')
            )
            return

        buttons_template = ButtonsTemplate(
            title='選擇操作',
            text='您希望如何處理這張圖片？',
            actions=[
                PostbackAction(label='直接發送', data='send_image'),
                PostbackAction(label='添加文字', data='add_text')
            ]
        )
        template_message = TemplateSendMessage(
            alt_text='選擇操作',
            template=buttons_template
        )
        line_bot_api.reply_message(
            event.reply_token,
            template_message
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    postback_data = event.postback.data

    if postback_data == 'send_image':
        if user_id in pending_texts and 'image_url' in pending_texts[user_id]:
            image_url = pending_texts[user_id]['image_url']
            send_image_to_group(image_url, user_id)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="圖片已成功發送到群組。")
            )
            del pending_texts[user_id]
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="未找到圖片，請重新上傳圖片")
            )

    elif postback_data == 'add_text':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='請發送您要添加的文字。')
        )
        pending_texts[user_id] = {'action': 'add_text'}

def reset_pending_state(user_id):
    if user_id in pending_texts:
        del pending_texts[user_id]
        print(f'Cleared pending texts for user {user_id}')

def upload_image_to_postimage(image_content):
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": os.getenv('IMGBB_API_KEY'),  # 使用環境變數
        }
        files = {
            'image': image_content.content
        }
        response = requests.post(url, data=payload, files=files)
        data = response.json()

        if response.status_code == 200 and data['status'] == 200:
            return data['data']['url']
        else:
            raise Exception(f"Failed to upload image, response: {data}")

    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

def send_image_to_group(image_url, user_id):
    global GROUP_ID
    try:
        if not GROUP_ID:
            raise Exception("GROUP_ID is empty or not set")

        print(f"Sending image to group {GROUP_ID}")

        # 嘗試發送圖片
        line_bot_api.push_message(
            GROUP_ID,
            TextSendMessage(text=f"圖片網址：{image_url}")
        )
        print(f"Image URL sent to group {GROUP_ID}")
        del pending_texts[user_id]

    except LineBotApiError as e:
        if e.status_code == 429:
            print("Reached monthly limit, sending URL instead.")
            # 發送圖片 URL 而不是直接發送圖片
            line_bot_api.push_message(
                GROUP_ID,
                TextSendMessage(text=f"圖片網址：{image_url}")
            )
        else:
            print(f"Error sending image URL to group: {e}")


def upload_and_send_image(image_url, user_id, text_message):
    try:
        line_bot_api.push_message(
            GROUP_ID,
            TextSendMessage(text=f"圖片網址：{image_url}\n附加的文字：{text_message}")
        )
        print(f"Image with text sent to group {GROUP_ID}")

    except LineBotApiError as e:
        if e.status_code == 429:
            print("Reached monthly limit, sending URL instead.")
            line_bot_api.push_message(
                GROUP_ID,
                TextSendMessage(text=f"圖片網址：{image_url}\n附加的文字：{text_message}（發送圖片失敗，達到限制）")
            )
        else:
            print(f"Error sending image with text to group: {e}")

if __name__ == "__main__":
    socketio.run(app, port=10000)
