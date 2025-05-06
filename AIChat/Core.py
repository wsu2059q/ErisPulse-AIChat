import asyncio
from openai import AsyncOpenAI
from typing import Optional, Callable
from datetime import datetime

class Main:
    def __init__(self, sdk, logger):
        self.sdk = sdk
        self.logger = logger
        self.AIChatConfig = sdk.env.get("AIChat", {})

        self.ai_prefix = self.AIChatConfig.get("prefix", "ai")
        self.base_url = self.AIChatConfig.get("base_url", None)
        self.token = self.AIChatConfig.get("key", None)
        self.model = self.AIChatConfig.get("model", None)
        self.system_prompt = self.AIChatConfig.get("system_prompt", "")
        self.ai_args = self.AIChatConfig.get("Args", {})

        if self.token is None or self.model is None or self.base_url is None:
            self.logger.error("AI接口, 令牌或模型 未设置，请检查配置文件")
            self.logger.warning("""在程序入口或env.py检查以下配置是否填写
                sdk.env.set("AIChat", {
                    "prefix": "/ai",
                    "base_url": "",
                    "key": "",
                    "model": "",
                    "Args": {
                        "temperature": 0.7,
                        "max_tokens": 1024
                    },
                })
            """)
        self.client = AsyncOpenAI(api_key=self.token, base_url=self.base_url)
        self.has_handle = False
        self.custom_handlers = []

        if hasattr(sdk, "NormalHandler"):
            sdk.NormalHandler.AddHandle(self.handle_yunhu_message)
            self.logger.info("成功注册NormalHandler消息处理")
            self.has_handle = True
        if hasattr(sdk, "OneBotMessageHandler"):
            sdk.OneBotMessageHandler.AddHandle(self.handle_onebot_message)
            self.logger.info("成功注册OneBotMessageHandler消息处理")
            self.has_handle = True
        if hasattr(sdk, "m_ServNormal"):
            self.logger.info("此模块仅支持异步消息处理器，请使用其它模块代替")

        if not self.has_handle:
            self.logger.warning("未找到任何可用的消息处理器")
    def AddStreamHandle(self, handler: Callable):
        self.custom_handlers.append(handler)
        self.logger.info("成功注册AI流式消息处理函数")

    async def handle_yunhu_message(self, data):
        message = data.get("event", {}).get("message", {}).get("content", {}).get("text", "")
        
        sender_info = data.get("event", {}).get("sender", {})
        sender_id = sender_info.get("senderId", "未知用户")
        sender_nickname = sender_info.get("senderNickname", "未知昵称")
        send_time_timestamp = data.get("event", {}).get("message", {}).get("sendTime", 0)
        try:
            send_time = datetime.fromtimestamp(send_time_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            self.logger.error(f"时间戳转换失败: {e}")
            send_time = "未知时间"

        context_info = (
            f"[用户信息] 用户ID: {sender_id}, 昵称: {sender_nickname}\n"
            f"[时间戳] 消息发送时间: {send_time}\n"
            f"[消息内容] {message}"
        )

        chat_type = data.get("event", {}).get("chat", {}).get("chatType", "")
        chat_id = data["event"]["chat"].get("groupId") or sender_id
        if chat_type == "bot" or self.ai_prefix.lower() in message.lower():
            response = await self.get_ai_response(chat_id, context_info)
            await self.send_response(data, response, source="yunhu")

    async def handle_onebot_message(self, data):
        raw_message = data.get("raw_message", "")
        message_type = data.get("message_type", "private")
        chat_id = data.get("group_id") or data.get("user_id")

        if message_type == "private" or self.ai_prefix in raw_message:
            response = await self.get_ai_response(chat_id, raw_message)
            await self.send_response(data, response, source="onebot")

    async def get_ai_response(self, chatId, message: str) -> str:
        has_store_model = False

        if self.token is None or self.model is None:
            msg = "AI 接口令牌或模型未设置，请检查配置文件"
            self.logger.error(msg)
            return msg

        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if hasattr(self.sdk, "AIChatMessageStore"):
            messages += await self.sdk.AIChatMessageStore.get_message_history(chatId)
            has_store_model = True
        else:
            self.logger.warning("未找到AI消息存储模块，将不保存历史对话")
        
        messages.append({"role": "user", "content": message})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **self.ai_args
            )

            ai_response = ""
            async for chunk in response:
                content = chunk.choices[0].delta.content or ""
                ai_response += content
                for handler in self.custom_handlers:
                    await handler(content)

            if has_store_model:
                await self.sdk.AIChatMessageStore.add_message(chatId, "user", message)
                await self.sdk.AIChatMessageStore.add_message(chatId, "assistant", ai_response)

            return ai_response
        except Exception as e:
            self.logger.error(f"AI接口调用异常: {str(e)}")
            return "AI接口调用异常，请检查日志"
    async def send_response(self, original_data, response, source: str):
        if source == "yunhu":
            if hasattr(self.sdk, "MessageSender"):
                send = self.sdk.MessageSender
                self.logger.info(f"[NormalHandler] 准备发送回复: {response}")
                chat_type = original_data.get("event", {}).get("chat", {}).get("chatType", "")

                recv_id = (
                    original_data["event"]["sender"]["senderId"]
                    if chat_type == "bot"
                    else original_data.get("event", {}).get("chat", {}).get("chatId")
                )

                recv_type = 'user' if chat_type == 'bot' else 'group'

                if recv_id and recv_type:
                    result = await send.Text(
                        recvId=recv_id,
                        recvType=recv_type,
                        content=response,
                    )
            else:
                self.logger.error("云湖消息发送模块（MessageSender）未找到，请确保该模块为正常状态")
        elif source == "onebot":
            if hasattr(self.sdk, "OneBotAdapter"):
                self.logger.info(f"[OneBotMessageHandler] 准备发送回复: {response}")
                message_type = original_data.get("message_type", "private")
                user_id = original_data.get("user_id")
                group_id = original_data.get("group_id")
                
                action = "send_msg"
                params = {
                    "message_type": message_type,
                    "user_id" if message_type == "private" else "group_id": user_id if message_type == "private" else group_id,
                    "message": response
                }

                await self.sdk.OneBotAdapter.send_action(action, params)
            else:
                self.logger.error("OneBot适配器模块未找到，请确保该模块为正常状态")
        else:
            self.logger.error(f"未知的消息来源: {source}")
