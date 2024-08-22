import logging

import os
import sys
import json
import re
import time
import asyncio

# 添加系统路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# 设置数据目录
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "QASystem",
)

from app.api import *
from app.config import owner_id
from app.switch import load_switch, save_switch


# 检查是否是群主
def is_group_owner(role):
    return role == "owner"


# 检查是否是管理员
def is_group_admin(role):
    return role == "admin"


# 检查是否有权限（管理员、群主或root管理员）
def is_authorized(role, user_id):
    is_admin = is_group_admin(role)
    is_owner = is_group_owner(role)
    return (is_admin or is_owner) or (user_id in owner_id)


# 异步加载知识库文件
async def load_knowledge_base(group_id):
    try:
        with open(
            os.path.join(DATA_DIR, f"{group_id}.json"), "r", encoding="utf-8"
        ) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# 异步保存知识库文件
async def save_knowledge_base(group_id, data):
    try:
        # 确保目录存在
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(
            os.path.join(DATA_DIR, f"{group_id}.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"保存知识库文件失败: {e}")
        return False
    return True


# 异步添加知识库条目
async def add_knowledge_base(group_id, keywords, question, answer):
    try:
        data = await load_knowledge_base(group_id)
        keyword_list = keywords.split("|")  # 分割多个关键词
        current_time = time.time()  # 获取当前时间

        for keyword in keyword_list:
            # 查找是否已有相同的关键词
            keyword_entry = next(
                (item for item in data if item["keyword"] == keyword), None
            )
            if keyword_entry:
                # 如果关键词已存在，添加或更新问题和答案
                keyword_entry["question"][question] = answer
            else:
                # 如果关键词不存在，创建新的关键词条目
                data.append(
                    {
                        "keyword": keyword,
                        "question": {question: answer},
                    }
                )
            # 更新关键词最后触发时间，防止立即触发
            keyword_last_triggered[keyword] = current_time

        return await save_knowledge_base(group_id, data)
    except Exception as e:
        logging.error(f"保存知识库文件失败: {e}")
        return False


# 异步删除知识库条目
async def delete_knowledge_base(group_id, keyword, question=None):
    data = await load_knowledge_base(group_id)
    for item in data:
        if item["keyword"] == keyword:
            if question:
                del item["question"][question]
                # 如果关键词下没有问题了，删除关键词
                if not item["question"]:
                    data.remove(item)
            else:
                data.remove(item)
            return await save_knowledge_base(group_id, data)
    return False


# 管理知识库命令处理
async def manage_knowledge_base(
    websocket, group_id, message_id, raw_message, user_id, role
):
    try:
        if is_authorized(role, user_id):
            # 处理开关命令
            if raw_message.startswith("qa-on"):
                if load_switch(group_id, "知识库"):
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已经开启了，无需重复开启",
                    )
                else:
                    save_switch(group_id, "知识库", True)
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已开启",
                    )
                return  # 确保处理完命令后返回

            elif raw_message.startswith("qa-off"):
                if not load_switch(group_id, "知识库"):
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已关闭，无需重复关闭",
                    )
                else:
                    save_switch(group_id, "知识库", False)
                    await send_group_msg(
                        websocket,
                        group_id,
                        f"[CQ:reply,id={message_id}] 知识库已关闭",
                    )
                return  # 确保处理完命令后返回

            # 识别添加知识库命令
            match = re.match(
                r"qa-add (.+?) (.+?) (.+)",
                raw_message,
                re.DOTALL,
            )
            if match:
                keywords = match.group(1)
                question = match.group(2)
                answer = match.group(3)
                if await add_knowledge_base(group_id, keywords, question, answer):
                    content = (
                        f"[CQ:reply,id={message_id}]"
                        + "添加成功\n"
                        + "关键词："
                        + keywords
                        + "\n"
                        + "问题："
                        + question
                        + "\n"
                        + "答案："
                        + answer
                    )
                    await send_group_msg(websocket, group_id, content)
                return  # 确保处理完命令后返回

            # 删除知识库某关键词下的某个问题
            match = re.match(r"qa-rm (.+?) (.+)", raw_message)
            if match:
                keyword = match.group(1)
                question = match.group(2)
                if await delete_knowledge_base(group_id, keyword, question):
                    content = (
                        f"[CQ:reply,id={message_id}]"
                        + "删除成功\n"
                        + "关键词："
                        + keyword
                        + "\n"
                        + "问题："
                        + question
                    )
                    await send_group_msg(websocket, group_id, content)
                return  # 确保处理完命令后返回

            # 删除知识库关键词下所有问题
            match = re.match(r"qa-rm (.+)", raw_message)
            if match:
                keyword = match.group(1)
                if await delete_knowledge_base(group_id, keyword):
                    content = (
                        f"[CQ:reply,id={message_id}]"
                        + "删除成功\n"
                        + "已删除关键词："
                        + keyword
                        + "下所有问题"
                    )
                    await send_group_msg(websocket, group_id, content)
                return  # 确保处理完命令后返回

    except Exception as e:
        logging.error(f"管理知识库失败: {e}")
        return False


# 关键词触发频率限制
KEYWORD_TRIGGER_LIMIT = 300  # 每个关键词每5分钟最多触发一次
keyword_last_triggered = {}


# 识别关键词返回问题
async def identify_keyword(websocket, group_id, message_id, raw_message):
    try:
        if load_switch(group_id, "知识库"):
            data = await load_knowledge_base(group_id)
            current_time = time.time()
            for item in data:
                if any(
                    keyword in raw_message for keyword in item["keyword"].split("|")
                ):
                    # 检查关键词触发频率限制
                    last_triggered = keyword_last_triggered.get(item["keyword"], 0)
                    if current_time - last_triggered < KEYWORD_TRIGGER_LIMIT:
                        logging.info(
                            f"关键词 {item['keyword']} 触发频率过高，剩余：{KEYWORD_TRIGGER_LIMIT - (current_time - last_triggered)}秒解锁，截断本次触发"
                        )
                        return

                    logging.info(f"识别到关键词: {item['keyword']}")
                    keyword_last_triggered[item["keyword"]] = current_time
                    question = item["question"]

                    # 优化：直接返回完全匹配的问题答案
                    if raw_message in question:
                        answer = question[raw_message]
                        answer = answer.replace("&#91;", "[").replace(
                            "&#93;", "]"
                        )  # 替换特殊字符
                        content = f"[CQ:reply,id={message_id}]" + answer
                        await send_group_msg(websocket, group_id, content)
                        return

                    question_list = "\n".join([f"{q}" for q, a in question.items()])
                    content = (
                        f"[CQ:reply,id={message_id}]"
                        + "识别到关键词，你可能想问:\n\n"
                        + question_list
                        + "\n\n"
                        + "如有需要请发送上述问题关键词"
                    )
                    await send_group_msg(websocket, group_id, content)
                    return

    except Exception as e:
        logging.error(f"识别知识库关键词异常: {e}")
        return False


# 识别问题返回答案
async def identify_question(websocket, group_id, message_id, raw_message):
    try:
        if load_switch(group_id, "知识库"):
            data = await load_knowledge_base(group_id)
            for item in data:
                question = item["question"]
                for q, a in question.items():
                    if q == raw_message:
                        logging.info(f"识别到问题: {q}")
                        a = a.replace("&#91;", "[").replace(
                            "&#93;", "]"
                        )  # 替换特殊字符
                        content = f"[CQ:reply,id={message_id}]" + a
                        await send_group_msg(websocket, group_id, content)
                        return True  # 返回True表示识别到问题
            return False
    except Exception as e:
        logging.error(f"识别知识库问题返回答案异常: {e}")
        return False


async def handle_qasystem_message_group(websocket, msg):
    try:
        group_id = msg.get("group_id", "")
        message_id = msg.get("message_id", "")
        raw_message = msg.get("raw_message", "")
        user_id = msg.get("user_id", "")
        role = msg.get("sender", {}).get("role", "")

        # 先尝试识别问题
        question_identified = await identify_question(
            websocket, group_id, message_id, raw_message
        )

        # 如果没有识别到问题，再尝试识别关键词
        if not question_identified:
            await asyncio.gather(
                manage_knowledge_base(
                    websocket, group_id, message_id, raw_message, user_id, role
                ),  # 管理知识库
                identify_keyword(
                    websocket, group_id, message_id, raw_message
                ),  # 识别关键词返回问题
            )

    except Exception as e:
        logging.error(f"知识库处理消息异常: {e}")
        return False
