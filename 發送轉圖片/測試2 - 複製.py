import os
import requests
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, ImageMessage, ImageSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# LINE Bot API credentials
line_bot_api = LineBotApi('F9ICmtWv1O6sXnv33re7wZE6XAeH7QEgpAO+/LS3Z/GbvdKA09krQf7sN1GLh3p8J7AA/JpLF7PM58FZ7ADA3TnF7RdSvxVdxA/1ybvlQGACVuyFpyuzIT5kgirE0FjrAVOnu7pHtVayiLAx3e/7mwdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('4698790a9e94fe30037737c09a9d3072')
GROUP_ID = 'C1b583c38ba492359f2c2cf8ca1d1e800'

IMGUR_CLIENT_ID = '6aab1dd4cdc087c'

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

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id

    # Retrieve image content
    image_content = line_bot_api.get_message_content(message_id)
    image_path = f'static/{message_id}.jpg'

    # Download image
    with open(image_path, 'wb') as fd:
        for chunk in image_content.iter_content():
            fd.write(chunk)

    print(f'Image successfully downloaded to {image_path}')

    # Upload image to Imgur
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
    with open(image_path, 'rb') as img_file:
        response = requests.post(
            "https://api.imgur.com/3/upload",
            headers=headers,
            files={"image": img_file}
        )
    if response.status_code == 200:
        img_url = response.json()['data']['link']
        print(f'Image successfully uploaded to Imgur: {img_url}')

        # Send image to group
        try:
            line_bot_api.push_message(
                GROUP_ID,
                ImageSendMessage(
                    original_content_url=img_url,
                    preview_image_url=img_url
                )
            )
            print('Image successfully sent to group.')
        except Exception as e:
            print(f'Error sending image to group: {e}')

        # Delete the local image file
        if os.path.exists(image_path):
            os.remove(image_path)
            print(f'Image successfully deleted from {image_path}')
    else:
        print(f'Failed to upload image to Imgur: {response.status_code}')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
