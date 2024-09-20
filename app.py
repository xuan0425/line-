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
from linebot.exceptions import InvalidSignatureError
import concurrent.futures
import requests
import json
import time
import random

app = Flask(__name__)
socketio = SocketIO(app, async_mode=None)

line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C3dca1e6da36d110cdfc734c47180e428'  

pending_texts = {}
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

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

@app.route('/')
def index():
    return "Hello, World!"

# 處理發送的圖片數量超過20張的情況
def check_image_count_and_delete():
    """檢查圖片數量，若超過20張，刪除舊的15張"""
    url = "https://api.imgbb.com/1/list"  # 假設有這個API，請替換為實際API
    response = requests.get(url, params={"key": "你的API密鑰"})
    data = response.json()

    if len(data['data']) > 20:
        # 獲取較舊的15張圖片
        images_to_delete = data['data'][:15]
        for img in images_to_delete:
            delete_image(img['id'])

def delete_image(image_id):
    """刪除指定ID的圖片"""
    delete_url = f"https://api.imgbb.com/1/delete/{image_id}"
    response = requests.post(delete_url, params={"key": "你的API密鑰"})
    if response.status_code == 200:
        print(f"Image {image_id} deleted successfully.")
    else:
        print(f"Failed to delete image {image_id}. Response: {response.text}")

@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message_event(event):
    """處理來自用戶的訊息或圖片，顯示操作按鈕"""
    user_id = event.source.user_id
    source_type = event.source.type

    buttons_template = ButtonsTemplate(
        title='選擇操作',
        text='請選擇您希望的操作',
        actions=[
            PostbackAction(label='直接發送圖片', data='send_image_direct'),
            PostbackAction(label='發送圖片後添加文字', data='send_image_with_text')
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
    data = event.postback.data

    if data == 'send_image_direct':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請發送圖片。")
        )
        pending_texts[user_id] = {'action': 'send_image_direct'}
    elif data == 'send_image_with_text':
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請發送圖片。")
        )
        pending_texts[user_id] = {'action': 'send_image_with_text'}

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    """處理用戶上傳的圖片"""
    user_id = event.source.user_id
    action = pending_texts.get(user_id, {}).get('action')

    if action == 'send_image_direct':
        image_url = upload_image_to_postimage(event.message.id)
        if image_url:
            send_image_to_group(image_url, user_id)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="圖片已成功發送到群組。")
            )
        reset_pending_state(user_id)

    elif action == 'send_image_with_text':
        image_url = upload_image_to_postimage(event.message.id)
        pending_texts[user_id]['image_url'] = image_url
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請發送要添加的文字。")
        )

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    """處理添加文字的情況"""
    user_id = event.source.user_id
    if user_id in pending_texts and pending_texts[user_id].get('action') == 'send_image_with_text':
        text_message = event.message.text
        image_url = pending_texts[user_id].get('image_url')
        if image_url:
            send_image_to_group(image_url, user_id, text_message)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="圖片和文字已成功發送到群組。")
            )
        reset_pending_state(user_id)

def reset_pending_state(user_id):
    """重置用戶的 pending_texts 狀態"""
    if user_id in pending_texts:
        del pending_texts[user_id]
        print(f'Cleared pending texts for user {user_id}')

def upload_image_to_postimage(message_id):
    """上傳圖片到外部圖像托管服務，並返回圖片URL"""
    try:
        image_content = line_bot_api.get_message_content(message_id)
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": "9084929272af9aef3bcbb7c7b8517f67",
        }
        files = {
            'image': image_content.content
        }
        response = requests.post(url, data=payload, files=files)
        data = response.json()

        if response.status_code == 200 and data['success']:
            imgur_url = data['data']['url']
            check_image_count_and_delete()  # 每次上傳完圖片後檢查數量
            print(f'Image uploaded successfully: {imgur_url}')
            return imgur_url
        else:
            print(f'Failed to upload image: {response.text}')
            return None

    except Exception as e:
        print(f'Error uploading image: {e}')
        return None

def send_image_to_group(image_url, user_id, text_message=None):
    """將圖片（和文字）發送到群組"""
    if image_url:
        try:
            print(f'Sending image with URL: {image_url}')

            messages = [ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )]

            if text_message:
                messages.append(TextSendMessage(text=text_message))

            line_bot_api.push_message(
                GROUP_ID,
                messages
            )
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text='圖片和文字已成功發送到群組。' if text_message else '圖片已成功發送到群組。')
            )
        except Exception as e:
            print(f'Error sending image and text to group: {e}')
    else:
        print('No image URL provided.')

if __name__ == "__main__":
    app.run(port=10000)
