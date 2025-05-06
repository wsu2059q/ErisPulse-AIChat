moduleInfo = {
    "meta": {
        "name": "AIChat",
        "version": "1.5.2",
        "description": "AI聊天模块, 适配异步的OneBot及云湖触发器",
        "author": "WSu2059",
        "license": "MIT",
        "homepage": "https://github.com/wsu2059q/ErisPulse-AIChat"
    },
    "dependencies": {
        "requires": [],
        "optional": [["OneBotMessageHandler", "MessageSender", "NormalHandler"]],
        "pip": ["openai"]
    }
}

from .Core import Main