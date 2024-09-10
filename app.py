import os
from flask import Flask, request, abort, send_from_directory
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
GROUP_ID = 'C1b583c38ba492359f2c2cf8ca1d1e800'  # 初始群組ID

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

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

    # 檢查是否為設定群組的指令
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
    else:
        # 忽略其他文字訊息
        pass

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id

    # 忽略群組中的所有圖片消息
    if event.source.type == 'group':
        return

    # 下載圖片
    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'
    with open(image_path, 'wb') as fd:
        for chunk in image_content.iter_content():
            fd.write(chunk)
    
    print(f'Image successfully downloaded to {image_path}')

    # 記錄用戶的待處理狀態
    pending_texts[user_id] = {'image_path': image_path}

    # 發送按鈕選單請用戶選擇是否要增加轉發文字
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
                print('Image successfully sent to group.')
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

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    if user_id in pending_texts:
        if user_message.lower() == '取消':
            del pending_texts[user_id]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='操作已取消。')
            )
            return
        
        # 用戶提供轉發文字
        image_path = pending_texts[user_id]['image_path']
        text_message = user_message
        imgur_url = upload_image_to_imgur(image_path)

        try:
            line_bot_api.push_message(
                GROUP_ID,
                [ImageSendMessage(
                    original_content_url=imgur_url,
                    preview_image_url=imgur_url
                ), TextSendMessage(text=text_message)]
            )
            print('Image and text successfully sent to group.')
        except Exception as e:
            print(f'Error sending image and text to group: {e}')

        # 刪除本地圖片
        os.remove(image_path)

        # 清除用戶的待處理狀態
        del pending_texts[user_id]

# 存儲用戶的待處理狀態
pending_texts = {}

def upload_image_to_imgur(image_path):
    from imgurpython import ImgurClient

    client_id = '6aab1dd4cdc087c'
    client_secret = 'a77d39b7994e6ad35be36bb564c907bf289ceb18	'
    client = ImgurClient(client_id, client_secret)

    response = client.upload_from_path(image_path, anon=True)
    return response['link']

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
