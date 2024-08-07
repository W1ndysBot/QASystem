import logging

import os
import sys
import json
import re


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
SWITCH_FILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "switch_status.json"
)

# 初始开关状态
qa_system_enabled = True


# 读取开关状态
def load_switch_status():
    global qa_system_enabled
    try:
        with open(SWITCH_FILE_PATH, "r", encoding="utf-8") as f:
            status = json.load(f)
            qa_system_enabled = status.get("qa_system_enabled", True)
    except FileNotFoundError:
        pass


# 保存开关状态
def save_switch_status():
    try:
        with open(SWITCH_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"qa_system_enabled": qa_system_enabled},
                f,
                ensure_ascii=False,
                indent=4,
            )
    except Exception as e:
        logging.error(f"保存开关状态失败: {e}")


# 在程序启动时加载开关状态
load_switch_status()


# 是否是群主
async def is_group_owner(role):
    return role == "owner"


# 是否是管理员
async def is_group_admin(role):
    return role == "admin"


# 是否是管理员或群主或root管理员
async def is_authorized(role, user_id):
    is_admin = await is_group_admin(role)
    is_owner = await is_group_owner(role)
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
async def add_knowledge_base(group_id, keyword, question, answer):
    try:
        data = await load_knowledge_base(group_id)

        # 查找是否已有相同的关键词
        keyword_entry = next(
            (item for item in data if item["keyword"] == keyword), None
        )
        if keyword_entry:
            # 如果关键词已存在，添加或更新问题和答案
            keyword_entry["question"][question] = answer
        else:
            # 如果关键词不存在，创建新的关键词条目
            data.append({"keyword": keyword, "question": {question: answer}})

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

        # 识别添加知识库命令
        if re.match(r"添加知识库 .* .* .*", raw_message):
            keyword = raw_message.split(" ")[1]
            question = raw_message.split(" ")[2]
            answer = raw_message.split(" ")[3]
            if await add_knowledge_base(group_id, keyword, question, answer):
                content = (
                    "[CQ:reply,id="
                    + str(message_id)  # 将 message_id 转换为字符串
                    + "]"
                    + "添加成功\n"
                    + "关键词："
                    + keyword
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
        elif re.match(r"删除知识库 .* .*", raw_message):
            keyword = raw_message.split(" ")[1]
            question = raw_message.split(" ")[2]
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
        elif re.match(r"删除知识库 .*", raw_message):
            keyword = raw_message.split(" ")[1]
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
        elif "知识库" in raw_message:
            content = (
                "[CQ:reply,id="
                + str(message_id)  # 将 message_id 转换为字符串
                + "]"
                + "无效的知识库命令"
                + "\n"
                + "请使用以下命令：\n"
                + "添加知识库 关键词 问题 答案\n"
                + "删除知识库 关键词 问题\n"
                + "删除知识库 关键词"
            )
            await send_group_msg(websocket, group_id, content)
            return True

        else:
            logging.info(f"未识别到管理知识库命令，跳过")
            return False

    except Exception as e:
        logging.error(f"管理知识库失败: {e}")
        return False


# 识别关键词返回问题
async def identify_keyword(websocket, group_id, message_id, raw_message):
    try:
        data = await load_knowledge_base(group_id)
        for item in data:
            if item["keyword"] in raw_message:
                logging.info(f"识别到关键词: {item['keyword']}")
                question = item["question"]
                question_list = "\n".join(
                    [f"{i}. {q}" for i, (q, a) in enumerate(question.items(), 1)]
                )
                content = (
                    "[CQ:reply,id="
                    + str(message_id)  # 将 message_id 转换为字符串
                    + "]"
                    + "识别到关键词，你可能想问:\n"
                    + question_list
                    + "\n"
                    + "如有需要请发送上述问题关键词"
                )
                await send_group_msg(websocket, group_id, content)
                return True
            else:
                logging.info(f"未识别到知识库关键词，跳过")
                return False

    except Exception as e:
        logging.error(f"识别关键词异常: {e}")
        return False


# 识别问题返回答案
async def identify_question(websocket, group_id, message_id, raw_message):
    try:
        data = await load_knowledge_base(group_id)
        for item in data:
            question = item["question"]
            for q, a in question.items():
                if q in raw_message:
                    content = (
                        "[CQ:reply,id="
                        + str(message_id)  # 将 message_id 转换为字符串
                        + "]"
                        + a
                    )
                    await send_group_msg(websocket, group_id, content)
                    return True
        return False
    except Exception as e:
        logging.error(f"识别问题返回答案异常: {e}")
        return False


# 仅root管理员可用的开关控制
async def toggle_qa_system(user_id, enable):
    if user_id in owner_id:
        global qa_system_enabled
        qa_system_enabled = enable
        save_switch_status()
        return True
    return False


async def handle_qasystem_message_group(websocket, msg):
    try:
        user_id = msg.get("user_id", "")
        group_id = msg.get("group_id", "")
        message_id = msg.get("message_id", "")
        raw_message = msg.get("raw_message", "")
        role = msg.get("role", "")

        # 判断是否是管理员或群主或root管理员
        if await is_authorized(role, user_id):
            # 管理知识库
            if await manage_knowledge_base(websocket, msg):
                return

            # 处理开关命令
            if re.match(r"开启知识库", raw_message):
                if await toggle_qa_system(user_id, True):
                    content = "[CQ:reply,id=" + str(message_id) + "] 知识库已开启"
                    await send_group_msg(websocket, group_id, content)
                    return True

            elif re.match(r"关闭知识库", raw_message):
                if await toggle_qa_system(user_id, False):
                    content = "[CQ:reply,id=" + str(message_id) + "] 知识库已关闭"
                    await send_group_msg(websocket, group_id, content)
                    return True

        # 检查知识库是否启用
        if not qa_system_enabled:
            content = "[CQ:reply,id=" + str(message_id) + "] 知识库功能已关闭"
            await send_group_msg(websocket, group_id, content)
            return False

        # 识别关键词返回问题
        await identify_keyword(websocket, group_id, message_id, raw_message)

        # 识别问题返回答案
        await identify_question(websocket, group_id, message_id, raw_message)

    except Exception as e:
        logging.error(f"知识库处理消息异常: {e}")
        return False
