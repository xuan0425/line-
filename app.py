import os
import threading
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, ImageSendMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction
)
from linebot.models.events import PostbackEvent
from linebot.exceptions import InvalidSignatureError
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientRateLimitError
import time

app = Flask(__name__)

# LINE Bot API credentials
line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  # 初始群組ID

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    print(f"Received request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@app.route('/<filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text

    print(f"Received message: {user_message}")

    # Check if the message is the command to set the group ID
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
    elif event.source.user_id in pending_texts:
        # Handle text message for adding text
        user_id = event.source.user_id
        if user_message.lower() == '取消':
            del pending_texts[user_id]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='操作已取消。')
            )
        else:
            image_path = pending_texts[user_id]['image_path']
            text_message = user_message
            
            # 使用 threading 執行上傳操作
            upload_thread = threading.Thread(target=upload_and_send_image, args=(user_id, image_path, text_message))
            upload_thread.start()

def upload_and_send_image(user_id, image_path, text_message=None):
    imgur_url = upload_image_to_imgur(image_path)

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

            # 回覆用戶發送成功
            if text_message:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text='圖片和文字已成功發送到群組。')
                )
            else:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )
        except Exception as e:
            print(f'Error sending image and text to group: {e}')

        # 刪除本地圖片
        os.remove(image_path)
        del pending_texts[user_id]

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    if event.source.type == 'group':
        return

    # Download the image
    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'
    with open(image_path, 'wb') as fd:
        for chunk in image_content.iter_content():
            fd.write(chunk)

    print(f'Image successfully downloaded to {image_path}')

    # Store user's pending status
    pending_texts[user_id] = {'image_path': image_path}

    # Send buttons template to ask for text
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
    line_bot_api.reply_message(
        event.reply_token,
        template_message
    )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data

    # 確保處理請求時不阻塞主流程
    if user_id in pending_texts:
        image_path = pending_texts[user_id]['image_path']
        imgur_url = upload_image_to_imgur(image_path)

        if data == 'send_image':
            try:
                # 發送圖片到群組
                line_bot_api.push_message(
                    GROUP_ID,
                    ImageSendMessage(
                        original_content_url=imgur_url,
                        preview_image_url=imgur_url
                    )
                )
                print('Image successfully sent to group.')

                # 回覆用戶發送成功
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )
            except Exception as e:
                print(f'Error sending image to group: {e}')

            # 刪除本地圖片
            os.remove(image_path)
            del pending_texts[user_id]
        
        elif data == 'add_text':
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )

# Store users' pending status
pending_texts = {}

def upload_image_to_imgur(image_path):
    client_id = '6aab1dd4cdc087c'
    client_secret = 'cc881c85b5dfcde2a1af7714fecef24cc1dccd71'
    client = ImgurClient(client_id, client_secret)

    try:
        response = client.upload_from_path(image_path, anon=True)
        return response['link']
    except ImgurClientRateLimitError:
        print("Imgur rate limit exceeded. Waiting before retrying...")
        time.sleep(60)  # Wait 60 seconds before retrying
        return upload_image_to_imgur(image_path)  # Retry uploading
    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
