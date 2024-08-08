import logging

import os
import sys
import json
import re
import time

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "QASystem",
)

from app.api import *
from app.config import owner_id

# 开关状态文件路径
SWITCH_FILE_PATH = os.path.join(DATA_DIR, "switch_status.json")


# 读取开关状态
def load_switch_status_file():
    try:
        with open(SWITCH_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# 保存开关状态
def save_switch_status_file(switch_status):
    try:
        with open(SWITCH_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(switch_status, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"保存开关状态文件失败: {e}")


# 仅root管理员可用的开关控制
async def toggle_qa_system(user_id, group_id, enable):
    if user_id in owner_id:
        switch_status = load_switch_status_file()
        switch_status[str(group_id)] = enable
        save_switch_status_file(switch_status)
        return True
    else:
        return False


# 是否是群主
def is_group_owner(role):
    return role == "owner"


# 是否是管理员
def is_group_admin(role):
    return role == "admin"


# 是否是管理员或群主或root管理员
def is_authorized(role, user_id):
    is_admin = is_group_admin(role)
    is_owner = is_group_owner(role)
    return (is_admin or is_owner) or (user_id in owner_id)


# 加载知识库文件
async def load_knowledge_base(group_id):
    try:
        with open(
            os.path.join(DATA_DIR, f"{group_id}.json"), "r", encoding="utf-8"
        ) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# 保存知识库文件
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


# 添加知识库
async def add_knowledge_base(group_id, keywords, question, answer):
    try:
        data = await load_knowledge_base(group_id)
        keyword_list = keywords.split("|")  # 分割多个关键词

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

        return await save_knowledge_base(group_id, data)
    except Exception as e:
        logging.error(f"保存知识库文件失败: {e}")
        return False


# 删除知识库
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


# 管理知识库
async def manage_knowledge_base(websocket, msg):
    try:
        group_id = msg.get("group_id", "")
        message_id = msg.get("message_id", "")
        raw_message = msg.get("raw_message", "")
        user_id = msg.get("user_id", "")
        role = msg.get("sender", {}).get("role", "")

        is_admin = is_group_admin(role)  # 是否是群管理员
        is_owner = is_group_owner(role)  # 是否是群主
        is_authorized = (is_admin or is_owner) or (
            user_id in owner_id
        )  # 是否是群主或管理员或root管理员

        # 处理开关命令
        if re.match(r"开启知识库|qaon", raw_message) and is_authorized:
            if await toggle_qa_system(user_id, group_id, True):
                content = "[CQ:reply,id=" + str(message_id) + "] 知识库已开启"
                await send_group_msg(websocket, group_id, content)
                return True

        elif re.match(r"关闭知识库|qaoff", raw_message) and is_authorized:
            if await toggle_qa_system(user_id, group_id, False):
                content = "[CQ:reply,id=" + str(message_id) + "] 知识库已关闭"
                await send_group_msg(websocket, group_id, content)
                return True

        # 检查知识库是否启用，默认关闭
        if not load_switch_status_file().get(str(group_id), False):
            logging.info("知识库已关闭，跳过处理")
            return True

        # 识别添加知识库命令
        match = re.match(
            r"添加知识库 (.+?) (.+?) (.+)|qaadd (.+?) (.+?) (.+)",
            raw_message,
            re.DOTALL,
        )
        if match and is_authorized:
            keywords = match.group(1) or match.group(4)
            question = match.group(2) or match.group(5)
            answer = match.group(3) or match.group(6)
            if await add_knowledge_base(group_id, keywords, question, answer):
                content = (
                    "[CQ:reply,id="
                    + str(message_id)  # 将 message_id 转换为字符串
                    + "]"
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
                return True

        # 删除知识库某关键词下的某个问题
        match = re.match(r"删除知识库 (.+?) (.+)|qadel (.+?) (.+)", raw_message)
        if match and is_authorized:
            keyword = match.group(1) or match.group(3)
            question = match.group(2) or match.group(4)
            if await delete_knowledge_base(group_id, keyword, question):
                content = (
                    "[CQ:reply,id="
                    + str(message_id)  # 将 message_id 转换为字符串
                    + "]"
                    + "删除成功\n"
                    + "关键词："
                    + keyword
                    + "\n"
                    + "问题："
                    + question
                )
                await send_group_msg(websocket, group_id, content)
                return True

        # 删除知识库关键词下所有问题
        match = re.match(r"删除知识库 (.+)|qadel (.+)", raw_message)
        if match and is_authorized:
            keyword = match.group(1) or match.group(2)
            if await delete_knowledge_base(group_id, keyword):
                content = (
                    "[CQ:reply,id="
                    + str(message_id)  # 将 message_id 转换为字符串
                    + "]"
                    + "删除成功\n"
                    + "已删除关键词："
                    + keyword
                    + "下所有问题"
                )
                await send_group_msg(websocket, group_id, content)
                return True

        # 无效命令的提示
        elif (
            "知识库" == raw_message
            or "qaadd" == raw_message
            or "qadel" == raw_message
            or "添加知识库" == raw_message
            or "删除知识库" == raw_message
        ) and is_authorized:
            content = (
                "[CQ:reply,id="
                + str(message_id)  # 将 message_id 转换为字符串
                + "]"
                + "无效的知识库命令"
                + "\n"
                + "请使用以下命令：\n"
                + "添加知识库 关键词 问题 答案\n"
                + "删除知识库 关键词 问题\n"
                + "删除知识库 关键词\n"
                + "或使用快捷命令：\n"
                + "qaadd 关键词 问题 答案\n"
                + "qadel 关键词 问题\n"
                + "qadel 关键词"
            )
            await send_group_msg(websocket, group_id, content)
            return True

        else:
            logging.info(f"未识别到管理知识库命令，跳过")
            return False

    except Exception as e:
        logging.error(f"管理知识库失败: {e}")
        return False


# 关键词触发频率限制
KEYWORD_TRIGGER_LIMIT = 60  # 每个关键词每分钟最多触发一次
keyword_last_triggered = {}


# 识别关键词返回问题
async def identify_keyword(websocket, group_id, message_id, raw_message):
    try:
        data = await load_knowledge_base(group_id)
        current_time = time.time()
        for item in data:
            if any(keyword in raw_message for keyword in item["keyword"].split("|")):
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
                question_list = "\n".join(
                    [f"{i}. {q}" for i, (q, a) in enumerate(question.items(), 1)]
                )
                content = (
                    "[CQ:reply,id="
                    + str(message_id)
                    + "]"
                    + "识别到关键词，你可能想问:\n"
                    + question_list
                    + "\n"
                    + "如有需要请发送上述问题关键词"
                )
                await send_group_msg(websocket, group_id, content)
                return True
        logging.info(f"未识别到知识库关键词，跳过")
        return False
    except Exception as e:
        logging.error(f"识别知识库关键词异常: {e}")
        return False


# 识别问题返回答案
async def identify_question(websocket, group_id, message_id, raw_message):
    try:
        data = await load_knowledge_base(group_id)
        for item in data:
            question = item["question"]
            for q, a in question.items():
                if q == raw_message:
                    content = "[CQ:reply,id=" + str(message_id) + "]" + a
                    await send_group_msg(websocket, group_id, content)
                    return True
        logging.info(f"未识别到知识库问题，跳过")
        return False
    except Exception as e:
        logging.error(f"识别知识库问题返回答案异常: {e}")
        return False


async def handle_qasystem_message_group(websocket, msg):
    try:
        user_id = msg.get("user_id", "")
        group_id = msg.get("group_id", "")
        message_id = msg.get("message_id", "")
        raw_message = msg.get("raw_message", "")

        # 管理知识库
        if await manage_knowledge_base(websocket, msg):
            return

        # 检查知识库是否启用，默认关闭
        if not load_switch_status_file().get(str(group_id), False):
            return

        # 识别关键词返回问题
        if await identify_keyword(websocket, group_id, message_id, raw_message):
            return  # 识别到关键词返回问题，防止继续往下识别出符合条件的答案

        # 识别问题返回答案
        await identify_question(websocket, group_id, message_id, raw_message)

    except Exception as e:
        logging.error(f"知识库处理消息异常: {e}")
        return False
