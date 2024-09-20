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
import httpx
import concurrent.futures
import os

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
            image_path = pending_texts[user_id]['image_path']
            text_message = user_message
            executor.submit(upload_and_send_image, image_path, user_id, text_message)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    if event.source.type == 'group':
        return

    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'
    
    # 確保 static 目錄存在
    if not os.path.exists('static'):
        os.makedirs('static')

    # 檢查檔案權限
    if not os.access('static', os.W_OK):
        print("沒有權限寫入 static 資料夾")
        return

    try:
        with open(image_path, 'wb') as fd:
            for chunk in image_content.iter_content():
                fd.write(chunk)

        print(f'Image successfully downloaded to {image_path}')
        pending_texts[user_id] = {'image_path': image_path}
        print(f"Updated pending_texts: {pending_texts}")  # 新增日誌
        
    except Exception as e:
        print(f'Error saving image: {e}')

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
            image_path = pending_texts[user_id]['image_path']
            executor.submit(upload_and_send_image, image_path, user_id)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="未找到圖片，請先發送圖片。")
            )

def upload_and_send_image(image_path, user_id, text_message=None):
    print(f"upload_and_send_image called with image_path: {image_path} and text_message: {text_message}")  # 新增日誌
    if not image_path:
        print('No image path provided. Aborting upload.')
        return

    print(f'Starting upload_and_send_image with {image_path}')  # Debugging line
    imgur_url = upload_image_to_postimage(image_path)
    
    print(f'Uploaded image URL: {imgur_url}')  # 新增日誌

    if imgur_url:
        send_image_to_group(imgur_url, user_id, text_message)
    else:
        print('Image upload failed. No URL returned.')

def send_image_to_group(imgur_url, user_id, text_message=None):
    if imgur_url:
        try:
            print(f'Sending image with URL: {imgur_url}')  # Debugging line

            messages = [ImageSendMessage(
                original_content_url=imgur_url,
                preview_image_url=imgur_url
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
