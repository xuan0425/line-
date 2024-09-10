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
import time

app = Flask(__name__)

# LINE Bot API credentials
line_bot_api = LineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')
GROUP_ID = 'C1e11e203e527b7f8e9bcb2d4437925b8'  # 初始群組ID

# GitHub API credentials
GITHUB_TOKEN = os.getenv('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')  # 從環境變數中讀取
g = Github(GITHUB_TOKEN)
repo = g.get_repo("xuan0425/123456")  # 替換為您的 GitHub 用戶名和倉庫名稱

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

            if github_url:
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
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片上傳失敗，請稍後再試。')
                )

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

        if data == 'send_image':
            github_url = upload_image_to_github(image_path)
            if github_url:
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
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='圖片上傳失敗，請稍後再試。')
                )

            # Delete local image and pending status
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

    # 獲取默認分支名稱
    default_branch = repo.default_branch

    # 構建文件路徑
    file_path = f"images/{image_name}"

    # 檢查文件是否已存在
    try:
        existing_file = repo.get_contents(file_path, ref=default_branch)
        print(f"File {file_path} already exists.")
        # 如果文件已存在，可以選擇不重新上傳，直接返回現有的URL
        # 或者根據需求進行更新。此處選擇不重新上傳
        return f"https://raw.githubusercontent.com/{repo.full_name}/{default_branch}/{file_path}"
    except github.GithubException.GithubException as e:
        if e.status == 404:
            # 文件不存在，創建新文件
            try:
                repo.create_file(file_path, "Upload image", encoded_content, branch=default_branch)
                print(f"Image uploaded to GitHub: {file_path}")
            except Exception as upload_error:
                print(f"Error uploading image: {upload_error}")
                return None
        else:
            # 其他錯誤
            print(f"Error checking file existence: {e}")
            return None

    # 刪除舊圖片，如果超過5張
    delete_old_images()

    # 返回圖片的 raw URL
    return f"https://raw.githubusercontent.com/{repo.full_name}/{default_branch}/{file_path}"

def delete_old_images():
    try:
        contents = repo.get_contents("images", ref=repo.default_branch)
        files = repo.get_contents("images", ref=repo.default_branch)

        # 如果 'images' 是文件夾，使用 repo.get_contents("images")
        files = repo.get_contents("images", ref=repo.default_branch)

        # 按照創建時間排序
        sorted_files = sorted(files, key=lambda x: x.last_modified if hasattr(x, 'last_modified') else x.created_at)

        if len(sorted_files) > 5:
            # 刪除最舊的文件
            oldest_file = sorted_files[0]
            repo.delete_file(oldest_file.path, "Delete old image", oldest_file.sha)
            print(f"Deleted old image: {oldest_file.path}")
    except Exception as e:
        print(f"Error deleting old images: {e}")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
