import os
import aiohttp
import asyncio
from flask import Flask, request, abort, send_from_directory, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, ImageSendMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction
)
from linebot.models.events import PostbackEvent
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# LINE Bot API credentials
line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=') 
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  # 初始群組ID

@app.route('/callback', methods=['POST'])
def callback():
    data = request.get_json()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(handle_event(data))
    except Exception as e:
        print(f"Error in callback: {e}")
        return jsonify({'error': str(e)}), 500
    return 'OK'

async def handle_event(data):
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    handler.handle(body, signature)

@app.route('/<filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/')
def index():
    return "LINE bot is running!"

@handler.add(MessageEvent, message=TextMessage)
async def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text

    print(f"Received message: {user_message}")

    if user_message.startswith('/設定群組'):
        if event.source.type == 'group':
            GROUP_ID = event.source.group_id
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"群組ID已更新為：{GROUP_ID}")
            )
            print(f"Group ID updated to: {GROUP_ID}")
        else:
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此指令只能在群組中使用。")
            )
    elif event.source.user_id in pending_texts:
        user_id = event.source.user_id
        if user_message.lower() == '取消':
            del pending_texts[user_id]
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='操作已取消。')
            )
        else:
            image_path = pending_texts[user_id]['image_path']
            text_message = user_message
            
            imgur_url = await upload_image_to_imgur(image_path)
            await send_image_to_group(imgur_url, user_id, text_message)

async def send_image_to_group(imgur_url, user_id, text_message=None):
    if imgur_url:
        try:
            messages = [ImageSendMessage(
                original_content_url=imgur_url,
                preview_image_url=imgur_url
            )]
            
            if text_message:
                messages.append(TextSendMessage(text=text_message))

            await line_bot_api.push_message(
                GROUP_ID,
                messages
            )
            print('Image and text successfully sent to group.')

            if text_message:
                await line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text='圖片和文字已成功發送到群組。')
                )
            else:
                await line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )
        except Exception as e:
            print(f'Error sending image and text to group: {e}')

        os.remove(pending_texts[user_id]['image_path'])
        del pending_texts[user_id]

@handler.add(MessageEvent, message=ImageMessage)
async def handle_image_message(event):
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
            PostbackAction(
                label='直接發送',
                data='send_image'
            ),
            PostbackAction(
                label='添加文字',
                data='add_text'
            )
        ]
    )
    template_message = TemplateSendMessage(
        alt_text='選擇操作',
        template=buttons_template
    )
    await line_bot_api.reply_message(
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
            imgur_url = await upload_image_to_imgur(image_path)

            if imgur_url:
                await line_bot_api.push_message(
                    GROUP_ID,
                    ImageSendMessage(
                        original_content_url=imgur_url,
                        preview_image_url=imgur_url
                    )
                )
                print('Image successfully sent to group.')

                await line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )

            os.remove(image_path)
            del pending_texts[user_id]
        
        elif data == 'add_text':
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )

pending_texts = {}

async def upload_image_to_imgur(image_path):
    client_id = '6aab1dd4cdc087c'
    headers = {'Authorization': f'Client-ID {client_id}'}

    try:
        async with aiohttp.ClientSession() as session:
            with open(image_path, 'rb') as image_file:
                data = {'image': image_file}
                async with session.post('https://api.imgur.com/3/upload', headers=headers, data=data) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        imgur_url = response_json['data']['link']
                        return imgur_url
                    else:
                        print(f'Error uploading image to Imgur: {response.status}')
                        return None
    except Exception as e:
        print(f'Exception uploading image to Imgur: {e}')
        return None

if __name__ == "__main__":
    app.run()
