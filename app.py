from quart import Quart, request, abort, jsonify
from linebot import AsyncLineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
import httpx
import logging

# 設置日誌記錄
logging.basicConfig(level=logging.DEBUG)

app = Quart(__name__)

# 初始化 AsyncLineBotApi
async_http_client = httpx.AsyncClient()
line_bot_api = AsyncLineBotApi('Xe4goaDprmptFyFWzYrTxX5TwO6bzAnvYrIGUGDxpE29pTzXeBmDmgsmLOlWSgmdAT8Kwh3ujnKC3InLDoStESGARbqQ3qTkNPlxNnqXIgrsIGSmEe7pKH4RmDzELH4mUoDhqEfdOOk++ACz8MsuegdB04t89/1O/w1cDnyilFU=', async_http_client=async_http_client)
handler = WebhookHandler('8763f65621c328f70d1334b4d4758e46')

@app.route("/callback", methods=["POST"])
async def callback():
    signature = request.headers.get('X-Line-Signature')
    body = await request.get_data(as_text=True)

    try:
        await handle_event(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        logging.error(f"Error in callback: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

    return 'OK'

async def handle_event(body, signature):
    if handler is not None:
        await handler.handle(body, signature)
    else:
        logging.error("WebhookHandler instance is None")

@handler.add(MessageEvent, message=TextMessage)
async def handle_text_message(event):
    try:
        user_message = event.message.text
        logging.debug(f"Received message: {user_message}")

        await line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"您發送了: {user_message}")
        )
    except Exception as e:
        logging.error(f"Error in handle_text_message: {e}", exc_info=True)

if __name__ == "__main__":
    # 使用 Quart 啟動應用程序
    app.run(port=10000, debug=True)
