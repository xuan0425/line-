import os
import base64
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, ImageSendMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction
)
from linebot.models.events import PostbackEvent
from linebot.exceptions import InvalidSignatureError
from github import Github

app = Flask(__name__)

# LINE Bot API credentials
line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  # 初始群組ID

# GitHub API credentials
g = Github("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")
repo = g.get_repo("xuan0425/123456")

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
            github_url = upload_image_to_github(image_path)

            try:
                line_bot_api.push_message(
                    GROUP_ID,
                    [ImageSendMessage(
                        original_content_url=github_url,
                        preview_image_url=github_url
                    ), TextSendMessage(text=text_message)]
                )
                print('Image and text successfully sent to group.')
            except Exception as e:
                print(f'Error sending image and text to group: {e}')

            # Delete local image
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

    if user_id in pending_texts:
        image_path = pending_texts[user_id]['image_path']
        github_url = upload_image_to_github(image_path)

        if data == 'send_image':
            try:
                line_bot_api.push_message(
                    GROUP_ID,
                    ImageSendMessage(
                        original_content_url=github_url,
                        preview_image_url=github_url
                    )
                )
                print('Image successfully sent to group.')
            except Exception as e:
                print(f'Error sending image to group: {e}')

            # Delete local image
            os.remove(image_path)
            del pending_texts[user_id]
        
        elif data == 'add_text':
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text='請發送您想轉發的文字。')
            )

# Store users' pending status
pending_texts = {}

def upload_image_to_github(image_path):
    image_name = os.path.basename(image_path)
    with open(image_path, "rb") as img_file:
        content = img_file.read()
        encoded_content = base64.b64encode(content).decode()

    # Upload image to GitHub repository's images directory
    repo.create_file(f"images/{image_name}", "Upload image", encoded_content)
    print(f"Image uploaded to GitHub: images/{image_name}")

    # Delete old images if more than 5
    delete_old_images()

    # Return the raw URL of the image
    return f"https://raw.githubusercontent.com/{repo.full_name}/main/images/{image_name}"

def delete_old_images():
    files = repo.get_contents("images")
    if len(files) > 5:
        # Delete the oldest image
        sorted_files = sorted(files, key=lambda x: x.created_at)
        oldest_file = sorted_files[0]
        repo.delete_file(oldest_file.path, "Delete old image", oldest_file.sha)
        print(f"Deleted old image: {oldest_file.path}")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
