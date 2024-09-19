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
import os

app = Flask(__name__)
socketio = SocketIO(app)

line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  

pending_texts = {}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"Error in callback: {e}")
        return jsonify({'error': str(e)}), 500

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    user_id = event.source.user_id

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

            imgur_url = await upload_image_to_postimage(image_path)
            if imgur_url:
                send_image_to_group(imgur_url, user_id, text_message)

def send_image_to_group(imgur_url, user_id, text_message=None):
    if imgur_url:
        try:
            messages = [ImageSendMessage(
                original_content_url=imgur_url,
                preview_image_url=imgur_url
            )]

            if text_message:
                messages.append(TextSendMessage(text=text_message))

            line_bot_api.push_message(
                GROUP_ID,
                messages
            )
            print('Image and text successfully sent to group.')

            line_bot_api.push_message(
                user_id,
                TextSendMessage(text='圖片和文字已成功發送到群組。' if text_message else '圖片已成功發送到群組。')
            )
        except Exception as e:
            print(f'Error sending image and text to group: {e}')

        os.remove(pending_texts[user_id]['image_path'])
        del pending_texts[user_id]

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
async def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data

    if user_id in pending_texts:
        image_path = pending_texts[user_id]['image_path']

        if data == 'send_image':
            imgur_url = await upload_image_to_postimage(image_path)

            if imgur_url:
                line_bot_api.push_message(
                    GROUP_ID,
                    ImageSendMessage(
                        original_content_url=imgur_url,
                        preview_image_url=imgur_url
                    )
                )
                print('Image successfully sent to group.')

                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )

            os.remove(image_path)
            del pending_texts[user_id]

        elif data == 'add_text':
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )

async def upload_image_to_postimage(image_path):
    url = 'https://postimages.org/json/upload'
    try:
        async with httpx.AsyncClient() as client:
            with open(image_path, 'rb') as image_file:
                files = {'file': image_file}
                response = await client.post(url, files=files)
                print(f'PostImage response: {response.text}')  # 打印完整的响应内容
                response_json = response.json()
                
                if response_json.get('status') == 'success':
                    return response_json['data']['url']
                else:
                    print('Error uploading image to PostImage:', response_json)
                    return None
    except Exception as e:
        print(f'Exception uploading image to PostImage: {e}')
        return None

if __name__ == "__main__":
    app.run(port=10000)
