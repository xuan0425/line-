import sys
from gevent import monkey
monkey.patch_all()  # 確保早期進行monkey patching

sys.setrecursionlimit(2000)  # 根據需要調整這個值
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
import os
import requests  # 這裡新增 requests 庫來處理圖片上傳

app = Flask(__name__)
socketio = SocketIO(app, async_mode=None)  # 使用同步模式

line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  

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

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text
    user_id = event.source.user_id

    print(f"Received message: {user_message}")

    if user_message.startswith('/設定群組'):
        if event.source.type == 'group':
            GROUP_ID = event.source.group_id
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
    elif user_id in pending_texts:
        if user_message.lower() == '取消':
            del pending_texts[user_id]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='操作已取消。')
            )
        else:
            image_url = pending_texts[user_id]['image_url']
            text_message = user_message
            executor.submit(upload_and_send_image, image_url, user_id, text_message)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    image_content = line_bot_api.get_message_content(message_id)

    try:
        # 將圖片上傳到外部服務
        image_url = upload_image_to_postimage(image_content)

        if image_url:
            print(f'Image successfully uploaded to {image_url}')
            pending_texts[user_id] = {'image_url': image_url}
            print(f"Updated pending_texts: {pending_texts}")  # 新增日誌
        else:
            raise Exception("Image upload failed")

    except Exception as e:
        print(f'Error processing image: {e}')

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
    print(f"Pending texts for user {user_id}: {pending_texts.get(user_id)}")  # 新增日誌

    if event.postback.data == 'send_image':
        if user_id in pending_texts:
            image_url = pending_texts[user_id]['image_url']
            executor.submit(upload_and_send_image, image_url, user_id)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="未找到圖片，請先發送圖片。")
            )

def upload_image_to_postimage(image_content):
    """將圖片上傳到外部圖像托管服務，並返回圖片URL"""
    try:
        # 這裡使用圖像托管 API 上傳圖片，以下是 ImgBB API 的示例
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
            print(f'Image uploaded successfully: {imgur_url}')
            return imgur_url
        else:
            print(f'Failed to upload image: {response.text}')
            return None

    except Exception as e:
        print(f'Error uploading image: {e}')
        return None

def upload_and_send_image(image_url, user_id, text_message=None):
    print(f"upload_and_send_image called with image_url: {image_url} and text_message: {text_message}")  # 新增日誌
    if not image_url:
        print('No image URL provided. Aborting upload.')
        return

    print(f'Starting upload_and_send_image with {image_url}')  # Debugging line

    send_image_to_group(image_url, user_id, text_message)

def send_image_to_group(image_url, user_id, text_message=None):
    if image_url:
        try:
            print(f'Sending image with URL: {image_url}')  # Debugging line

            messages = [ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )]

            if text_message:
                messages.append(TextSendMessage(text=text_message))

            response = line_bot_api.push_message(
                GROUP_ID,
                messages
            )
            print(f'Successfully sent to group. Response: {response}')  # Debugging line

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
