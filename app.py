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
    print(f"收到請求: {body}, 簽名: {signature}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("簽名驗證失敗。")
        abort(400)

    return 'OK'

@app.route('/<filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    global GROUP_ID
    user_message = event.message.text
    user_id = event.source.user_id
    print(f"接收到文字消息: {user_message} 來自用戶: {user_id}")

    # Check if the message is the command to set the group ID
    if user_message.startswith('/設定群組'):
        if event.source.type == 'group':
            GROUP_ID = event.source.group_id
            print(f"群組ID已更新為：{GROUP_ID}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"群組ID已更新為：{GROUP_ID}")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="此指令只能在群組中使用。")
            )
    elif user_id in pending_texts:
        if user_message.lower() == '取消':
            del pending_texts[user_id]
            print(f"用戶 {user_id} 已取消操作。")
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

def upload_and_send_image(user_id, image_path, text_message):
    print(f"開始上傳圖片，圖片路徑: {image_path}")
    imgur_url = upload_image_to_imgur(image_path)

    if imgur_url:
        try:
            line_bot_api.push_message(
                GROUP_ID,
                [ImageSendMessage(
                    original_content_url=imgur_url,
                    preview_image_url=imgur_url
                ), TextSendMessage(text=text_message)]
            )
            print(f"圖片和文字成功發送到群組：{GROUP_ID}")
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text='圖片和文字已成功發送到群組。')
            )
        except Exception as e:
            print(f'Error sending image and text to group: {e}')

        # 刪除本地圖片
        os.remove(image_path)
        print(f"本地圖片已刪除：{image_path}")
        del pending_texts[user_id]
    else:
        print("上傳圖片失敗。")
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text="圖片上傳失敗，請稍後再試。")
        )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    print(f"接收到圖片消息，ID: {message_id} 來自用戶: {user_id}")

    if event.source.type == 'group':
        print("圖片來自群組，忽略處理。")
        return

    # Download the image
    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'
    try:
        with open(image_path, 'wb') as fd:
            for chunk in image_content.iter_content():
                fd.write(chunk)
        print(f"圖片已保存至 {image_path}")
    except Exception as e:
        print(f"圖片下載失敗: {e}")

    # Store user's pending status
    pending_texts[user_id] = {'image_path': image_path}
    print(f"用戶 {user_id} 的圖片保存狀態已更新。")

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
    try:
        line_bot_api.reply_message(
            event.reply_token,
            template_message
        )
        print("選擇操作的按鈕模板已發送。")
    except Exception as e:
        print(f"回覆按鈕模板時發生錯誤: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    print(f"收到 Postback: {data}, 來自用戶 {user_id}")

    if user_id in pending_texts:
        image_path = pending_texts[user_id]['image_path']
        imgur_url = upload_image_to_imgur(image_path)

        if data == 'send_image':
            try:
                line_bot_api.push_message(
                    GROUP_ID,
                    ImageSendMessage(
                        original_content_url=imgur_url,
                        preview_image_url=imgur_url
                    )
                )
                print(f"圖片成功發送到群組。")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片已成功發送到群組。')
                )
            except Exception as e:
                print(f'發送圖片到群組時發生錯誤: {e}')

            # Delete local image
            os.remove(image_path)
            print(f"本地圖片已刪除：{image_path}")
            del pending_texts[user_id]
        
        elif data == 'add_text':
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )
            print("已請求用戶發送轉發文字。")

# Store users' pending status
pending_texts = {}

def upload_image_to_imgur(image_path):
    client_id = '6aab1dd4cdc087c'
    client_secret = 'cc881c85b5dfcde2a1af7714fecef24cc1dccd71'
    client = ImgurClient(client_id, client_secret)

    try:
        response = client.upload_from_path(image_path, anon=True)
        imgur_url = response['link']
        print(f"Imgur URL: {imgur_url}")
        return imgur_url
    except ImgurClientRateLimitError:
        print("Imgur rate limit exceeded. Waiting before retrying...")
        time.sleep(60)  # Wait 60 seconds before retrying
        return upload_image_to_imgur(image_path)  # Retry uploading
    except Exception as e:
        print(f"Error uploading image: {e}")
        return None

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
