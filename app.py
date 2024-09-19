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
import traceback

app = Flask(__name__)
socketio = SocketIO(app, async_mode=None)  # 使用同步模式

line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'   

pending_texts = {}

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    print(f"Received body: {body}")
    print(f"Received signature: {signature}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature")
        abort(400)
    except Exception as e:
        print("Error in callback:", e)
        return jsonify({'error': str(e)}), 500

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

    # 檢查是否為設置群組指令
    if user_message.startswith('/設定群組'):
        if event.source.type == 'group':
            global GROUP_ID
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
            # 使用 executor.submit 而不是 asyncio.run
            executor.submit(upload_and_send_image, image_path, user_id, text_message)

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

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    if event.source.type == 'group':
        return

    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'
    with open(image_path, 'wb') as fd:
        for chunk in image_content.iter_content():
            fd.write(chunk)

    print(f'Image successfully downloaded to {image_path}')

    pending_texts[user_id] = {'image_path': image_path}

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
    data = event.postback.data

    print(f'Postback event data: {data}')  # Debugging line

    if user_id in pending_texts:
        image_path = pending_texts[user_id]['image_path']

        if data == 'send_image':
            print('Handling send_image postback')  # Debugging line
            executor.submit(upload_and_send_image, image_path, user_id)

        elif data == 'add_text':
            print('Handling add_text postback')  # Debugging line
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )

def upload_image_to_postimage(image_path):
    url = 'https://postimages.org/json/upload'
    try:
        with open(image_path, 'rb') as image_file:
            files = {'file': image_file}
            response = httpx.post(url, files=files)
            print(f'PostImage response: {response.text}')  # Debugging line
            response_json = response.json()

            if response_json.get('status') == 'success':
                print(f'Image URL: {response_json["data"]["url"]}')  # Debugging line
                return response_json['data']['url']
            else:
                print('Error uploading image to PostImage:', response_json)
                return None
    except Exception as e:
        print(f'Exception uploading image to PostImage: {e}')
        return None

def upload_and_send_image(image_path, user_id, text_message=None):
    print(f'Starting upload_and_send_image with {image_path}')  # Debugging line
    imgur_url = upload_image_to_postimage(image_path)
    print(f'Image uploaded to: {imgur_url}')  # Debugging line
    if imgur_url:
        send_image_to_group(imgur_url, user_id, text_message)

if __name__ == "__main__":
    app.run(port=10000)
