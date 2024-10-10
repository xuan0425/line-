import sys
from gevent import monkey
monkey.patch_all()

import time  # 用於延遲操作
sys.setrecursionlimit(2000)
from flask import Flask, request, abort, jsonify
from flask_socketio import SocketIO
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate,
    PostbackAction, ImageMessage, PostbackEvent
)
from linebot.exceptions import InvalidSignatureError, LineBotApiError
import concurrent.futures
import requests
import os
import csv

app = Flask(__name__)
socketio = SocketIO(app, async_mode=None)

line_bot_api = LineBotApi(os.getenv('LINE_BOT_API'))
handler = WebhookHandler(os.getenv('LINE_HANDLER'))

pending_texts = {}
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

api_usage_count = 0

def track_api_usage():
    global api_usage_count
    api_usage_count += 1
    print(f"API requests count: {api_usage_count}")

# 讀取 CSV 文件以獲取所有群組 ID
def read_group_ids():
    group_ids = []
    try:
        with open('group_id.csv', 'r') as file:
            reader = csv.reader(file)
            group_ids = [row[0] for row in reader if row]  # 確保每行有內容
    except FileNotFoundError:
        print("CSV file not found, using default group.")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
    
    return group_ids

# 保存新的群組 ID 到 CSV 文件
def save_group_id(new_group_id):
    group_ids = read_group_ids()
    if group_ids is None:
        group_ids = []

    if new_group_id in group_ids:
        return False  # 如果 ID 已存在，返回 False

    try:
        with open('group_id.csv', 'a') as file:
            writer = csv.writer(file)
            writer.writerow([new_group_id])
    except Exception as e:
        print(f"Error writing to CSV file: {e}")
    
    return True  # 如果 ID 不存在，成功保存

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
    user_message = event.message.text
    source_type = event.source.type
    user_id = event.source.user_id  # 確保 user_id 被正確初始化

    if source_type == 'group':
        if user_message.startswith('/設定群組'):
            group_id = event.source.group_id
            if save_group_id(group_id):
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"群組ID已新增：{group_id}")
                )
                print(f"Group ID added: {group_id}")
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"群組ID {group_id} 已存在。")
                )
                print(f"Group ID {group_id} already exists.")
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
                    executor.submit(upload_and_send_image, image_url, user_id, text_message)  # 傳遞 user_id
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text='文字已成功添加。')
                    )
                else:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text='找不到圖片，請重新上傳。')
                    )
                    del pending_texts[user_id]  # 清除失敗的暫存狀態
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

            # 延遲3秒後發送
            time.sleep(3)

            send_image_to_groups(image_url, user_id)
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
            "key": os.getenv('IMGBB_API_KEY'),
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

# 發送圖片到所有群組
def send_image_to_groups(image_url, user_id):
    group_ids = read_group_ids()
    if not group_ids:
        print("No group IDs found")
        return

    for group_id in group_ids:
        try:
            line_bot_api.push_message(
                group_id,
                TextSendMessage(text=f"圖片網址：{image_url}")
            )
            print(f"Image URL sent to group {group_id}")
        except LineBotApiError as e:
            print(f"Error sending image URL to group {group_id}: {e}")
    reset_pending_state(user_id)

def upload_and_send_image(image_url, user_id, text_message):
    group_ids = read_group_ids()
    if not group_ids:
        print("No group IDs found")
        return

    for group_id in group_ids:
        try:
            line_bot_api.push_message(
                group_id,
                TextSendMessage(text=f"圖片網址：{image_url}\n附加的文字：{text_message}")
            )
            print(f"Image with text sent to group {group_id}")
        except LineBotApiError as e:
            print(f"Error sending image with text to group {group_id}: {e}")
    reset_pending_state(user_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
